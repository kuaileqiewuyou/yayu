"""Managed local GPT-SoVITS API process for the desktop application."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from PySide6.QtCore import QObject, QProcess, QTimer, Signal


@dataclass(frozen=True, slots=True)
class GPTSoVITSApiLaunchSpec:
    program: str
    arguments: tuple[str, ...]
    working_directory: str


def is_managed_local_api_url(server_url: str) -> bool:
    """Return whether the configured URL is the local API managed by this project."""
    parsed = urlsplit(server_url.strip())
    return (
        parsed.scheme in {"http", "https"}
        and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        and (parsed.port or (443 if parsed.scheme == "https" else 80)) == 9880
    )


def build_gpt_sovits_api_launch_spec(
    config_path: str | Path,
    *,
    bind_address: str = "127.0.0.1",
    port: int = 9880,
) -> GPTSoVITSApiLaunchSpec:
    """Resolve the bundled Python and api_v2 entrypoint from the ignored local YAML."""
    resolved_config = Path(config_path).resolve()
    if not resolved_config.is_file():
        raise FileNotFoundError(f"找不到 GPT-SoVITS 本地配置：{resolved_config}")

    with resolved_config.open("r", encoding="utf-8") as stream:
        raw = yaml.safe_load(stream) or {}
    custom = raw.get("custom") or {}
    bert_base_path = str(custom.get("bert_base_path") or "").strip()
    if not bert_base_path:
        raise ValueError("GPT-SoVITS 本地配置缺少 custom.bert_base_path")

    package_root = Path(bert_base_path).resolve().parents[2]
    python_path = package_root / "runtime" / "python.exe"
    api_path = package_root / "api_v2.py"
    for required_path in (python_path, api_path):
        if not required_path.is_file():
            raise FileNotFoundError(f"找不到 GPT-SoVITS 必需文件：{required_path}")

    return GPTSoVITSApiLaunchSpec(
        program=str(python_path),
        arguments=(
            str(api_path),
            "-c",
            str(resolved_config),
            "-a",
            bind_address,
            "-p",
            str(port),
        ),
        working_directory=str(package_root),
    )


class GPTSoVITSApiProcessController(QObject):
    """Start and stop only the local API process created by this application."""

    state_changed = Signal(str, str)

    def __init__(self, project_root: str | Path, parent: QObject | None = None):
        super().__init__(parent)
        self._config_path = Path(project_root) / "data" / "config" / "gpt_sovits_api.local.yaml"
        self._stopping = False
        self._output_tail = ""
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._process.started.connect(lambda: self.state_changed.emit("running", "GPT-SoVITS API 进程已启动，正在加载模型"))
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)
        self._process.readyReadStandardOutput.connect(self._capture_output)

    def is_running(self) -> bool:
        return self._process.state() != QProcess.ProcessState.NotRunning

    def start(self) -> None:
        if self.is_running():
            return
        try:
            spec = build_gpt_sovits_api_launch_spec(self._config_path)
        except Exception as exc:
            self.state_changed.emit("error", str(exc))
            return

        self._stopping = False
        self._output_tail = ""
        self._process.setProgram(spec.program)
        self._process.setArguments(list(spec.arguments))
        self._process.setWorkingDirectory(spec.working_directory)
        self.state_changed.emit("starting", "正在启动 GPT-SoVITS API 并加载模型")
        self._process.start()

    def stop(self) -> None:
        if not self.is_running():
            self.state_changed.emit("stopped", "GPT-SoVITS API 未运行")
            return
        self._stopping = True
        self.state_changed.emit("stopping", "正在停止 GPT-SoVITS API")
        self._process.terminate()
        QTimer.singleShot(3000, self._kill_if_needed)

    def shutdown(self) -> None:
        """Synchronously release a process owned by the application during window close."""
        if not self.is_running():
            return
        self._stopping = True
        self._process.terminate()
        if not self._process.waitForFinished(2000):
            self._process.kill()
            self._process.waitForFinished(2000)

    def _kill_if_needed(self) -> None:
        if self.is_running():
            self._process.kill()

    def _capture_output(self) -> None:
        chunk = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if not chunk:
            return
        self._output_tail = (self._output_tail + chunk)[-4000:]
        print(chunk, end="")

    def _on_finished(self, exit_code: int, _exit_status: QProcess.ExitStatus) -> None:
        self._capture_output()
        if self._stopping:
            self.state_changed.emit("stopped", "GPT-SoVITS API 已停止")
            return
        detail = self._last_output_line() or f"GPT-SoVITS API 已退出（代码 {exit_code}）"
        self.state_changed.emit("error", detail)

    def _on_error(self, _error: QProcess.ProcessError) -> None:
        if not self._stopping:
            self.state_changed.emit("error", self._process.errorString())

    def _last_output_line(self) -> str:
        lines = [line.strip() for line in self._output_tail.splitlines() if line.strip()]
        return lines[-1] if lines else ""

