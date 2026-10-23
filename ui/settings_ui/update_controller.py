"""Explicit, cancellable update jobs; no network work runs on the GUI thread."""
from __future__ import annotations

import re
import json
import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication, QMessageBox


# A forcibly deleted owner must never destroy a still-running QThread. Normal
# window closure instead cancels the job and waits asynchronously in closeEvent.
_LIVE_WORKERS: set[QThread] = set()


class _UpdateWorker(QThread):
    progress = Signal(object)
    phase = Signal(str)

    def __init__(self, task):
        super().__init__()
        self.task = task
        self.cancelled = threading.Event()
        self.result = None
        self.error = ""

    def run(self):
        try:
            self.result = self.task(self)
        except Exception as exc:
            # Only deliberate release-client errors are suitable for display.
            # Unexpected transport exceptions can include headers or credentials.
            try:
                from core.updates.releases import UpdateError
                from core.updates.installer import UpdateError as InstallError
            except ImportError:
                safe_errors = ()
            else:
                safe_errors = (UpdateError, InstallError)
            self.error = str(exc) if isinstance(exc, safe_errors) else "更新操作失败，请检查网络或 GitHub 权限后重试。"
            self.error = re.sub(r"(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]+", "[已隐藏令牌]", self.error)


class UpdateController(QObject):
    update_ready = Signal(object)

    def __init__(self, owner, panel, *, root: Path | None = None,
                 client_factory=None, credentials_api=None, installer_api=None):
        super().__init__(owner)
        self.owner, self.panel = owner, panel
        self.root = Path(root or panel.root).resolve()
        self._client_factory = client_factory
        self._credentials_api = credentials_api
        self._installer_api = installer_api
        self._worker = None
        self._operation = ""
        self._info = None
        self._prepared = None
        self._finalizing = False
        self._launched = False
        self._update_process = None
        self._previous_update_process = None
        self._exit_deadline = 0.0
        self._exit_started = 0.0
        self._recovery_required = False
        self._closing = False
        self._portable = (self.root / "runtime" / "python.exe").is_file()
        if self._portable:
            self._portable = self._installer().is_portable_install(self.root)
        if not self._portable:
            panel.mode_hint.setText("当前为源码或非完整便携目录，可以检查新版；自动安装仅支持完整的 Windows 便携版。")
        panel.check_button.clicked.connect(self.check)
        panel.install_button.clicked.connect(self.install)
        panel.cancel_button.clicked.connect(self.cancel)
        panel.save_token_button.clicked.connect(self.save_token)
        panel.clear_token_button.clicked.connect(self.clear_token)
        self._refresh()

    @property
    def busy(self) -> bool:
        return self._worker is not None or self._finalizing

    def _credentials(self):
        if self._credentials_api is None:
            from core.updates import credentials
            self._credentials_api = credentials
        return self._credentials_api

    def _installer(self):
        if self._installer_api is None:
            from core.updates import installer
            self._installer_api = installer
        return self._installer_api

    def _client(self):
        factory = self._client_factory
        if factory is None:
            from core.updates.releases import GitHubReleaseClient
            factory = GitHubReleaseClient
        return factory(token=self._credentials().get_token(self.root))

    def _refresh(self):
        locked = self.busy or self._launched
        self.panel.check_button.setEnabled(not locked)
        self.panel.install_button.setVisible(self._info is not None)
        self.panel.install_button.setEnabled(bool(self._info) and self._portable and not locked and not self._recovery_required)
        self.panel.cancel_button.setVisible(self.busy)
        self.panel.cancel_button.setEnabled(self._operation not in ("launch", "discard"))
        self.panel.save_token_button.setEnabled(not locked)
        self.panel.clear_token_button.setEnabled(not locked)
        self.panel.token_input.setEnabled(not locked)
        if self._info:
            self.panel.install_button.setText(f"更新到 {self._info.version}")

    def _start(self, operation, task):
        if self.busy or self._launched:
            return
        self._operation = operation
        worker = _UpdateWorker(task)
        self._worker = worker
        _LIVE_WORKERS.add(worker)
        worker.progress.connect(self._progress)
        worker.phase.connect(self.panel.status_label.setText)
        worker.finished.connect(self._finished)
        worker.finished.connect(lambda: _LIVE_WORKERS.discard(worker))
        self.panel.progress.setRange(0, 0)
        self.panel.progress.show()
        self.panel.cancel_button.setEnabled(True)
        self._refresh()
        worker.start()

    @Slot()
    def check(self):
        if self.busy or self._launched:
            return
        if not self._previous_process_stopped():
            return
        self._closing = False
        self.panel.status_label.setText("正在检查 GitHub 最新正式版本…")
        self._start("check", lambda worker: self._client().check(self.panel.current_version))

    @Slot()
    def install(self):
        if self.busy or self._launched or self._info is None or not self._portable or self._recovery_required:
            return
        if not self._previous_process_stopped():
            return
        self._closing = False
        if not self._confirm_install():
            return
        info = self._info
        self.panel.status_label.setText("正在下载更新…")

        def task(worker):
            with tempfile.TemporaryDirectory(prefix="yayu-update-download-") as folder:
                archive = self._client().download(
                    info, Path(folder) / info.asset_name,
                    progress=lambda *values: worker.progress.emit(values),
                    cancelled=worker.cancelled.is_set,
                )
                if worker.cancelled.is_set():
                    return None
                worker.phase.emit("正在校验并准备更新，个人数据保持原位…")
                prepared = self._installer().prepare_update(
                    archive, self.root, info.version, info.sha256,
                    progress=lambda *values: worker.progress.emit(values),
                )
                return prepared

        self._start("install", task)

    def _confirm_install(self):
        from ui.settings_ui.dialogs import SettingsMessageBox
        dialog = SettingsMessageBox(self.owner)
        dialog.setWindowTitle("安装软件更新")
        dialog.setText(f"保存并退出，更新到 {self._info.version}？")
        dialog.setInformativeText(
            "更新会自动备份程序并在原路径重启，保留原来的角色、配置和聊天记录。"
            "请先关闭另外单独打开的芽语主界面或设置窗口；下载期间仍可使用当前窗口。"
        )
        cancel = dialog.addButton("暂不更新", QMessageBox.ButtonRole.RejectRole)
        proceed = dialog.addButton("下载并更新", QMessageBox.ButtonRole.AcceptRole)
        dialog.setDefaultButton(cancel)
        dialog.exec()
        accepted = dialog.clickedButton() is proceed
        dialog.deleteLater()
        return accepted

    @Slot()
    def cancel(self):
        if self._worker:
            if self._operation in ("launch", "discard"):
                return
            self._worker.cancelled.set()
            self.panel.status_label.setText("正在取消，等待当前操作安全结束…")
            self.panel.cancel_button.setEnabled(False)
        elif self._finalizing:
            self._finalizing = False
            self._discard_prepared(self._prepared, "已取消更新，当前版本和个人数据未改动。")

    def shutdown(self) -> bool:
        """Cancel before window closure, without blocking the Qt event loop."""
        self._closing = True
        if self._finalizing:
            self.cancel()
        if self._worker is not None:
            self.cancel()
            return False
        return True

    @Slot(object)
    def _progress(self, values):
        if len(values) >= 2 and all(isinstance(v, (int, float)) for v in values[:2]):
            current, total = values[:2]
            if total > 0:
                self.panel.progress.setRange(0, 100)
                self.panel.progress.setValue(max(0, min(100, int(current / total * 100))))
                return
        self.panel.progress.setRange(0, 0)

    @Slot()
    def _finished(self):
        worker = self._worker
        if worker is None:
            return
        worker.wait()
        self._worker = None
        was_cancelled = worker.cancelled.is_set()
        result, error = worker.result, worker.error
        worker.deleteLater()
        self.panel.progress.hide()
        self._refresh()
        if self._operation == "discard":
            if not self._closing:
                self.panel.status_label.setText(self._cleanup_message if not error else "更新已停止，暂存清理未完成，请重新启动后恢复。")
            return
        if self._operation == "launch":
            if error:
                self._discard_prepared(self._prepared, error)
            else:
                self._update_process = result
                self._complete_exit()
            return
        if (self._closing or was_cancelled) and self._operation == "install" and result is not None:
            self._discard_prepared(result, "已取消更新，当前版本和个人数据未改动。")
            return
        if self._closing:
            return
        if was_cancelled:
            self.panel.status_label.setText("已取消更新，当前版本和个人数据未改动。")
        elif error:
            self.panel.status_label.setText(error)
            if any(word in error for word in ("令牌", "权限", "私有", "授权")):
                self.panel.credentials_toggle.setChecked(True)
        elif self._operation == "check":
            self._info = result
            if result is None:
                self.panel.status_label.setText("已经是最新正式版本。")
            else:
                suffix = "请下载便携版使用自动更新。" if not self._portable else "点击更新即可下载、安装并重启。"
                self.panel.status_label.setText(f"发现新版本 {result.version}。{suffix}")
            self._refresh()
        elif result is not None:
            self._prepared = result
            self.update_ready.emit(result)
            self._prepare_exit()

    def _prepare_exit(self):
        if getattr(self.owner, "_settings_dirty", False) and not self.owner._save_config(silent=True):
            self._discard_prepared(self._prepared, "配置尚未保存，更新已暂停。修正配置后可重新更新。")
            return
        memory = getattr(self.owner, "memory_tab", None)
        if memory is not None and not memory.confirm_pending_edits():
            self._discard_prepared(self._prepared, "更新已暂停，请先保存或完成记忆编辑。")
            return
        self._finalizing = True
        self._refresh()
        self._wait_memory_and_launch()

    def _wait_memory_and_launch(self):
        if not self._finalizing or self._closing:
            return
        memory = getattr(self.owner, "memory_tab", None)
        if memory is not None and not memory.close_service():
            self.panel.status_label.setText("正在等待后台记忆任务结束，然后退出更新…")
            QTimer.singleShot(100, self, self._wait_memory_and_launch)
            return
        self._finalizing = False
        self.panel.status_label.setText("正在启动独立更新程序，请稍候…")
        self._start("launch", lambda worker: self._installer().launch_update(self._prepared))

    def _discard_prepared(self, prepared, message):
        self._prepared = None
        self._cleanup_message = message
        if prepared is None:
            self.panel.status_label.setText(message)
            self._refresh()
            return
        self.panel.status_label.setText("正在安全清理更新暂存文件…")
        self._start("discard", lambda worker: self._installer().discard_prepared(prepared))

    def _complete_exit(self):
        self._launched = True
        self.owner._update_exit_prepared = True
        self.panel.status_label.setText("更新已准备，正在保存聊天并退出；随后自动安装并重启。")
        self._exit_started = time.monotonic()
        plan = self._read_status_file(Path(self._prepared.plan_path)) if self._prepared is not None else {}
        wait_timeout = plan.get("wait_timeout", 120)
        if not isinstance(wait_timeout, (int, float)) or not 0 < wait_timeout <= 600:
            wait_timeout = 120
        self._exit_deadline = self._exit_started + wait_timeout + 30
        self._refresh()
        app = QApplication.instance()
        if app is not None:
            app.closeAllWindows()
            # closeAllWindows honours closeEvent; quit only after they accepted.
            QTimer.singleShot(100, self, self._quit_when_closed)

    def _quit_when_closed(self):
        if not self._launched:
            return
        app = QApplication.instance()
        if app is None:
            return
        prepared = self._prepared
        state = ""
        if prepared is not None:
            state = self._read_status_file(Path(prepared.plan_path).parent / "journal.json").get("state", "")
        if not isinstance(state, str):
            state = ""
        retryable_states = {"failed-before-install", "cancelled-before-install", "launch-cancelled", "rolled-back"}
        if state in retryable_states and (self.root / ".yayu-update-pending.json").exists():
            # Journal publication precedes marker removal. Do not classify that
            # short atomic-write window as a permanently failed recovery.
            still_running = self._update_process is None or self._update_process.poll() is None
            if still_running and time.monotonic() < self._exit_deadline:
                self.panel.status_label.setText("本次更新已停止，正在等待更新程序释放恢复标记…")
                QTimer.singleShot(200, self, self._quit_when_closed)
                return
        if state in retryable_states or state == "recovery-required":
            self._restore_after_stopped_update(state)
            return
        if self._update_process is not None and self._update_process.poll() is not None:
            self._restore_after_stopped_update(state)
            return
        if not any(window.isVisible() for window in app.topLevelWidgets()):
            app.quit()
            return
        if time.monotonic() >= self._exit_deadline:
            self._restore_after_stopped_update("unconfirmed")
            return
        if time.monotonic() - self._exit_started >= 2:
            self.panel.status_label.setText(
                "正在等待主界面保存并关闭；请完成未结束的操作，并关闭其余芽语窗口。"
                "等待超时会停止更新，不会强制结束程序。"
            )
        QTimer.singleShot(200, self, self._quit_when_closed)

    @staticmethod
    def _read_status_file(path):
        try:
            if not path.is_file() or path.stat().st_size > 32 * 1024:
                return {}
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, UnicodeError):
            return {}

    def _restore_after_stopped_update(self, state):
        """A refused/slow close must not permanently lock the settings controls."""
        self._previous_update_process = self._update_process
        self._update_process = None
        self._prepared = None
        self._launched = False
        self._closing = False
        self._exit_deadline = 0.0
        self.owner._update_exit_prepared = False
        safe_retry = state in {"failed-before-install", "cancelled-before-install", "launch-cancelled", "rolled-back"}
        safe_retry = safe_retry and not (self.root / ".yayu-update-pending.json").exists()
        self._recovery_required = not safe_retry
        if safe_retry:
            if state == "rolled-back":
                message = "更新未完成，已恢复旧版程序；个人数据仍保留。关闭其他芽语窗口后可重试更新。"
            else:
                message = "未能完成退出，本次更新已停止，当前程序和个人数据未改动。请先关闭其他芽语窗口再重试。"
        else:
            message = "更新状态尚未确认，已停止等待退出。请关闭芽语所有窗口后重新启动以恢复，备份与恢复文件会保留。"
            self.panel.mode_hint.setText("上次更新需要恢复，暂不能再次安装。请关闭所有芽语窗口后重新启动。")
        self.panel.status_label.setText(message)
        self._refresh()
        self.owner.show()

    def _previous_process_stopped(self):
        process = self._previous_update_process
        if process is not None and process.poll() is None:
            self.panel.status_label.setText("独立更新程序仍在退出；请先关闭其更新结果提示，再重试。")
            return False
        self._previous_update_process = None
        return True

    @Slot()
    def save_token(self):
        if self.busy or self._launched:
            return
        token = self.panel.token_input.text().strip()
        if not token:
            self.panel.status_label.setText("请先填写 GitHub 访问令牌。")
            return
        try:
            self._credentials().save_token(self.root, token)
        except Exception:
            self.panel.status_label.setText("令牌未能保存，请确认 Windows 本机加密存储可用。")
            return
        self.panel.token_input.clear()
        self.panel.status_label.setText("GitHub 令牌已在本机加密保存，可再次检查更新。")

    @Slot()
    def clear_token(self):
        if self.busy or self._launched:
            return
        try:
            credentials = self._credentials()
            if hasattr(credentials, "clear_token"):
                credentials.clear_token(self.root)
            else:
                credentials.save_token(self.root, "")
        except Exception:
            self.panel.status_label.setText("无法清除已保存令牌，请检查本机文件访问权限。")
            return
        self.panel.token_input.clear()
        self.panel.status_label.setText("本机保存的令牌已清除；仍可使用已有的 gh 登录。")
