"""Qt update flows use fake releases and isolated paths, never private config."""
from pathlib import Path
from types import SimpleNamespace
import json
import threading
import time

import pytest
from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from ui.settings_ui.system_tab import build_system_tab
from ui.settings_ui.update_controller import UpdateController
from ui.settings_ui.update_panel import UpdatePanel


@pytest.fixture
def qapp(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


def wait_for(qapp, predicate, timeout=7000):
    deadline = time.monotonic() + timeout / 1000
    while not predicate() and time.monotonic() < deadline:
        qapp.processEvents()
        QTest.qWait(5)
    assert predicate()


class FakeCredentials:
    def __init__(self):
        self.token = None
        self.calls = []

    def get_token(self, root):
        self.calls.append(("get", root))
        return self.token

    def save_token(self, root, token):
        self.calls.append(("save", root))
        self.token = token

    def clear_token(self, root):
        self.calls.append(("clear", root))
        self.token = None


class FakeOwner(QWidget):
    def __init__(self):
        super().__init__()
        self._settings_dirty = False
        self.saved = 0
        self.save_result = True

    def _save_config(self, *, silent):
        assert silent is True
        self.saved += 1
        return self.save_result


@pytest.fixture
def make_update(qapp, tmp_path):
    created = []

    def make(client, *, portable=False, installer=None):
        root = tmp_path / str(len(created))
        root.mkdir()
        (root / "VERSION").write_text("1.0.3", encoding="utf-8")
        if portable:
            (root / "runtime").mkdir()
            (root / "runtime" / "python.exe").touch()
        if installer is not None:
            if not hasattr(installer, "is_portable_install"):
                installer.is_portable_install = lambda root: portable
            if not hasattr(installer, "discard_prepared"):
                installer.discard_prepared = lambda prepared: None
        owner = FakeOwner()
        panel = UpdatePanel(owner, root=root)
        credentials = FakeCredentials()
        controller = UpdateController(
            owner, panel, root=root, client_factory=lambda **kwargs: client,
            credentials_api=credentials, installer_api=installer,
        )
        created.append((owner, panel, controller))
        return owner, panel, controller, credentials

    yield make
    for owner, panel, controller in created:
        controller.cancel()
        wait_for(qapp, lambda: not controller.busy)
        owner.close()
        owner.deleteLater()
    qapp.processEvents()


def info():
    return SimpleNamespace(version="1.0.4", asset_name="Yayu-1.0.4-windows-x64.zip", sha256="a" * 64)


def test_update_panel_and_controller_do_not_lookup_token_or_network_on_creation(qapp, make_update):
    class Client:
        def check(self, current):
            pytest.fail("must not check automatically")

    owner, panel, controller, credentials = make_update(Client())
    assert panel.current_version == "1.0.3"
    assert "1.0.3" in panel.version_label.text()
    assert credentials.calls == []
    assert not controller.busy
    assert panel.token_input.echoMode() == panel.token_input.EchoMode.Password
    assert panel.token_input.property("settingsIndependent") is True
    assert panel.credentials_widget.isHidden()
    panel.credentials_toggle.click()
    assert not panel.credentials_widget.isHidden()
    assert owner._settings_dirty is False


def test_check_uses_worker_and_keeps_gui_responsive(qapp, make_update):
    gate = threading.Event()
    ids = []

    class Client:
        def check(self, current):
            ids.append(threading.get_ident())
            assert current == "1.0.3"
            gate.wait(2)
            return info()

    owner, panel, controller, credentials = make_update(Client())
    controller.check()
    try:
        wait_for(qapp, lambda: bool(ids))
        fired = []
        QTimer.singleShot(0, lambda: fired.append(True))
        wait_for(qapp, lambda: bool(fired))
        assert not panel.check_button.isEnabled()
        assert controller.busy
        assert ids[0] != threading.get_ident()
    finally:
        gate.set()
    wait_for(qapp, lambda: not controller.busy)
    assert "1.0.4" in panel.status_label.text()
    assert not panel.install_button.isEnabled()
    assert "源码" in panel.mode_hint.text()
    assert owner._settings_dirty is False


def test_latest_check_has_no_install_and_can_retry_after_failure(qapp, make_update):
    calls = []

    class Client:
        def check(self, current):
            calls.append(current)
            if len(calls) == 1:
                raise RuntimeError("Authorization: Bearer SHOULD_NOT_APPEAR")
            return None

    owner, panel, controller, credentials = make_update(Client())
    controller.check()
    wait_for(qapp, lambda: not controller.busy)
    assert "失败" in panel.status_label.text()
    assert "SHOULD_NOT_APPEAR" not in panel.status_label.text()
    assert panel.check_button.isEnabled()
    controller.check()
    wait_for(qapp, lambda: not controller.busy)
    assert "最新" in panel.status_label.text()
    assert panel.install_button.isHidden()


def test_private_release_authorization_error_opens_access_settings(qapp, make_update):
    from core.updates.releases import UpdateError

    class Client:
        def check(self, current):
            raise UpdateError("仓库为私有，请设置有读取权限的 GitHub 令牌。")

    owner, panel, controller, credentials = make_update(Client())
    controller.check()
    wait_for(qapp, lambda: not controller.busy)
    assert panel.credentials_toggle.isChecked()
    assert not panel.credentials_widget.isHidden()
    assert "最新" not in panel.status_label.text()


def test_cancel_and_shutdown_wait_for_worker_without_destroying_it(qapp, make_update):
    gate = threading.Event()
    entered = threading.Event()

    class Client:
        def check(self, current):
            entered.set()
            gate.wait(2)
            return info()

    owner, panel, controller, credentials = make_update(Client())
    controller.check()
    try:
        wait_for(qapp, entered.is_set)
        assert controller.shutdown() is False
        assert controller.busy
    finally:
        gate.set()
    wait_for(qapp, lambda: not controller.busy)
    assert controller.shutdown() is True
    assert controller._info is None
    controller.check()
    wait_for(qapp, lambda: not controller.busy)
    assert "发现" in panel.status_label.text()


def test_token_save_and_clear_are_independent_and_do_not_show_token(qapp, make_update):
    owner, panel, controller, credentials = make_update(SimpleNamespace())
    panel.token_input.setText("github_pat_LOCAL_ONLY")
    panel.save_token_button.click()
    assert credentials.token == "github_pat_LOCAL_ONLY"
    assert panel.token_input.text() == ""
    assert "github_pat_" not in panel.status_label.text()
    assert owner._settings_dirty is False
    panel.clear_token_button.click()
    assert credentials.token is None
    assert owner._settings_dirty is False


def test_download_prepare_runs_in_worker_then_saves_before_launch(qapp, make_update, monkeypatch):
    calls = []

    class Client:
        def check(self, current):
            return info()

        def download(self, release, destination, *, progress, cancelled):
            assert not cancelled()
            calls.append(("download", threading.get_ident()))
            progress(5, 10)
            destination.write_bytes(b"isolated test zip")
            return destination

    class Installer:
        def prepare_update(self, archive, root, version, sha256, *, progress):
            calls.append(("prepare", threading.get_ident()))
            assert archive.is_file()
            assert version == "1.0.4"
            return SimpleNamespace(plan_path=root / "plan.json", backup_dir=root / "backup")

        def launch_update(self, prepared):
            calls.append(("launch", threading.get_ident()))
            assert owner.saved == 1

    owner, panel, controller, credentials = make_update(Client(), portable=True, installer=Installer())
    owner._settings_dirty = True
    monkeypatch.setattr(controller, "_confirm_install", lambda: True)
    monkeypatch.setattr(QApplication, "closeAllWindows", lambda self: calls.append(("close", threading.get_ident())))
    monkeypatch.setattr(controller, "_quit_when_closed", lambda: None)
    controller.check()
    wait_for(qapp, lambda: not controller.busy)
    assert panel.install_button.isEnabled()
    controller.install()
    wait_for(qapp, lambda: controller._launched)
    assert [call[0] for call in calls] == ["download", "prepare", "launch", "close"]
    assert all(tid != threading.get_ident() for name, tid in calls[:2])
    assert calls[2][1] != threading.get_ident()
    assert owner._update_exit_prepared is True


def test_failed_config_save_prevents_helper_launch(qapp, make_update, monkeypatch):
    launches = []
    installer = SimpleNamespace(launch_update=lambda prepared: launches.append(prepared))
    owner, panel, controller, credentials = make_update(SimpleNamespace(), portable=True, installer=installer)
    owner._settings_dirty = True
    owner.save_result = False
    controller._prepared = object()
    controller._prepare_exit()
    wait_for(qapp, lambda: not controller.busy)
    assert launches == []
    assert "尚未保存" in panel.status_label.text()
    assert not controller._launched


def test_pending_memory_edits_prevent_helper_launch(qapp, make_update):
    launches = []
    installer = SimpleNamespace(launch_update=lambda prepared: launches.append(prepared))
    owner, panel, controller, credentials = make_update(SimpleNamespace(), portable=True, installer=installer)
    owner.memory_tab = SimpleNamespace(confirm_pending_edits=lambda: False)
    controller._prepared = object()
    controller._prepare_exit()
    wait_for(qapp, lambda: not controller.busy)
    assert launches == []
    assert "记忆编辑" in panel.status_label.text()


def test_cancel_after_prepare_discards_stage_without_launch(qapp, make_update, monkeypatch):
    gate = threading.Event()
    entered = threading.Event()
    discarded, launched = [], []

    class Client:
        def check(self, current):
            return info()

        def download(self, release, destination, **kwargs):
            destination.write_bytes(b"test")
            return destination

    class Installer:
        def is_portable_install(self, root):
            return True

        def prepare_update(self, *args, **kwargs):
            entered.set()
            gate.wait(3)
            return "prepared"

        def discard_prepared(self, prepared):
            discarded.append(prepared)

        def launch_update(self, prepared):
            launched.append(prepared)

    owner, panel, controller, credentials = make_update(Client(), portable=True, installer=Installer())
    monkeypatch.setattr(controller, "_confirm_install", lambda: True)
    controller.check()
    wait_for(qapp, lambda: not controller.busy)
    controller.install()
    try:
        wait_for(qapp, entered.is_set)
        controller.cancel()
    finally:
        gate.set()
    wait_for(qapp, lambda: not controller.busy)
    assert discarded == ["prepared"]
    assert launched == []
    assert "已取消" in panel.status_label.text()


def test_memory_service_finishes_before_launch_and_can_cancel_wait(qapp, make_update):
    discarded, launched = [], []
    installer = SimpleNamespace(
        launch_update=lambda prepared: launched.append(prepared),
        discard_prepared=lambda prepared: discarded.append(prepared),
    )
    owner, panel, controller, credentials = make_update(SimpleNamespace(), portable=True, installer=installer)
    owner.memory_tab = SimpleNamespace(confirm_pending_edits=lambda: True, close_service=lambda: False)
    controller._prepared = "prepared"
    controller._prepare_exit()
    assert controller.busy
    assert launched == []
    assert "记忆任务" in panel.status_label.text()
    controller.cancel()
    wait_for(qapp, lambda: not controller.busy)
    assert discarded == ["prepared"]
    assert launched == []


def test_download_failure_keeps_window_and_update_retryable(qapp, make_update, monkeypatch):
    class Client:
        def check(self, current):
            return info()

        def download(self, *args, **kwargs):
            raise RuntimeError("Authorization: SECRET")

    installer = SimpleNamespace()
    owner, panel, controller, credentials = make_update(Client(), portable=True, installer=installer)
    monkeypatch.setattr(controller, "_confirm_install", lambda: True)
    controller.check()
    wait_for(qapp, lambda: not controller.busy)
    controller.install()
    wait_for(qapp, lambda: not controller.busy)
    assert panel.install_button.isEnabled()
    assert not controller._launched
    assert "SECRET" not in panel.status_label.text()
    assert owner.saved == 0


def test_system_builder_exposes_update_card_without_requiring_a_real_config(qapp):
    parts = build_system_tab(SimpleNamespace())
    assert parts.update_panel.objectName() == "software_update_panel"
    parts.widget.deleteLater()


def test_settings_dirty_tracking_skips_update_token_without_loading_private_config(qapp):
    from ui.settings_ui.window import SettingsWindow
    owner = FakeOwner()
    owner._mark_settings_dirty = lambda *args: setattr(owner, "_settings_dirty", True)
    panel = UpdatePanel(owner)
    SettingsWindow._connect_editor_change(owner, panel.token_input)
    QTest.keyClicks(panel.token_input, "github_pat_LOCAL_ONLY")
    assert not owner._settings_dirty
    owner.deleteLater()


class RefusingChatWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.refuse_close = True
        self.close_requests = 0

    def closeEvent(self, event):
        self.close_requests += 1
        if self.refuse_close:
            event.ignore()
        else:
            super().closeEvent(event)


def prepare_exit_monitor(controller, owner):
    work = controller.root / "fake-update-work"
    work.mkdir()
    plan = work / "plan.json"
    plan.write_text(json.dumps({"wait_timeout": 1}), encoding="utf-8")
    controller._prepared = SimpleNamespace(plan_path=plan, backup_dir=work / "backup")
    controller._info = info()
    process = SimpleNamespace(returncode=None)
    process.poll = lambda: process.returncode
    controller._update_process = process
    return work, process


def test_refused_chat_close_recovers_buttons_when_helper_times_out(qapp, make_update, monkeypatch):
    owner, panel, controller, credentials = make_update(SimpleNamespace(), portable=True, installer=SimpleNamespace())
    work, process = prepare_exit_monitor(controller, owner)
    chat = RefusingChatWindow()
    owner.show()
    chat.show()
    monkeypatch.setattr(QApplication, "closeAllWindows", lambda app: (owner.close(), chat.close()))
    try:
        controller._complete_exit()
        assert chat.isVisible()
        assert chat.close_requests == 1
        assert controller._launched
        assert not panel.install_button.isEnabled()
        (work / "journal.json").write_text(json.dumps({"state": "failed-before-install"}), encoding="utf-8")
        process.returncode = 1
        controller._quit_when_closed()
        assert not controller._launched
        assert not controller._recovery_required
        assert owner.isVisible()
        assert panel.check_button.isEnabled()
        assert panel.install_button.isEnabled()
        assert not owner._update_exit_prepared
        assert controller._prepared is None
        assert "本次更新已停止" in panel.status_label.text()
    finally:
        chat.refuse_close = False
        chat.close()
        chat.deleteLater()


def test_failed_helper_result_prompt_must_close_before_starting_another_update(qapp, make_update, monkeypatch):
    owner, panel, controller, credentials = make_update(SimpleNamespace(), portable=True, installer=SimpleNamespace())
    work, process = prepare_exit_monitor(controller, owner)
    (work / "journal.json").write_text(json.dumps({"state": "failed-before-install"}), encoding="utf-8")
    monkeypatch.setattr(QApplication, "closeAllWindows", lambda app: None)
    controller._complete_exit()
    controller._quit_when_closed()
    confirmed = []
    monkeypatch.setattr(controller, "_confirm_install", lambda: confirmed.append(True) or False)
    controller.install()
    assert confirmed == []
    assert "结果提示" in panel.status_label.text()
    process.returncode = 1
    controller.install()
    assert confirmed == [True]


def test_hung_close_monitor_stops_and_requires_recovery_without_killing_process(qapp, make_update, monkeypatch):
    owner, panel, controller, credentials = make_update(SimpleNamespace(), portable=True, installer=SimpleNamespace())
    work, process = prepare_exit_monitor(controller, owner)
    owner.show()
    monkeypatch.setattr(QApplication, "closeAllWindows", lambda app: None)
    controller._complete_exit()
    controller._exit_deadline = 0
    controller._quit_when_closed()
    assert process.poll() is None
    assert not controller._launched
    assert controller._recovery_required
    assert panel.check_button.isEnabled()
    assert not panel.install_button.isEnabled()
    assert "重新启动以恢复" in panel.status_label.text()
    # A previously scheduled timer cannot restart the indefinite exit loop.
    controller._quit_when_closed()
    assert controller._exit_deadline == 0


def test_pending_recovery_never_enables_another_install(qapp, make_update, monkeypatch):
    owner, panel, controller, credentials = make_update(SimpleNamespace(), portable=True, installer=SimpleNamespace())
    work, process = prepare_exit_monitor(controller, owner)
    (work / "journal.json").write_text(json.dumps({"state": "recovery-required"}), encoding="utf-8")
    (controller.root / ".yayu-update-pending.json").write_text("{}", encoding="utf-8")
    process.returncode = 2
    monkeypatch.setattr(QApplication, "closeAllWindows", lambda app: None)
    controller._complete_exit()
    controller._quit_when_closed()
    assert controller._recovery_required
    assert not panel.install_button.isEnabled()
    assert (controller.root / ".yayu-update-pending.json").is_file()
    assert (work / "journal.json").is_file()


def test_terminal_journal_waits_for_pending_marker_to_clear(qapp, make_update, monkeypatch):
    owner, panel, controller, credentials = make_update(SimpleNamespace(), portable=True, installer=SimpleNamespace())
    work, process = prepare_exit_monitor(controller, owner)
    (work / "journal.json").write_text(json.dumps({"state": "failed-before-install"}), encoding="utf-8")
    marker = controller.root / ".yayu-update-pending.json"
    marker.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(QApplication, "closeAllWindows", lambda app: None)
    controller._complete_exit()
    controller._quit_when_closed()
    assert controller._launched
    assert not controller._recovery_required
    assert "释放恢复标记" in panel.status_label.text()
    marker.unlink()
    process.returncode = 1
    controller._quit_when_closed()
    assert not controller._launched
    assert not controller._recovery_required
    assert panel.install_button.isEnabled()
