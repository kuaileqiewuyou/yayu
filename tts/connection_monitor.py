"""Non-blocking GPT-SoVITS API availability monitoring for the Qt UI."""
from __future__ import annotations

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


def gpt_sovits_health_url(server_url: str) -> str:
    """Return a harmless FastAPI docs endpoint for a configured GPT-SoVITS URL."""
    normalized = server_url.strip().rstrip("/")
    if normalized.endswith("/tts"):
        normalized = normalized[:-4]
    return f"{normalized}/docs" if normalized else ""


class GPTSoVITSConnectionMonitor(QObject):
    """Periodically check whether the configured GPT-SoVITS HTTP API responds."""

    status_changed = Signal(str, str)

    def __init__(self, parent: QObject | None = None, *, timeout_ms: int = 2500):
        super().__init__(parent)
        self._health_url = ""
        self._active_reply: QNetworkReply | None = None
        self._timeout_ms = timeout_ms
        self._network = QNetworkAccessManager(self)

    def configure(self, server_url: str) -> None:
        self._health_url = gpt_sovits_health_url(server_url)
        if not self._health_url:
            self.stop()
            self.status_changed.emit("not_configured", "尚未配置 GPT-SoVITS 服务地址")
            return

    def stop(self) -> None:
        reply = self._active_reply
        if reply is None:
            return
        self._active_reply = None
        try:
            reply.finished.disconnect()
        except (RuntimeError, TypeError):
            pass
        reply.abort()
        reply.deleteLater()

    def check_now(self) -> None:
        if not self._health_url or self._active_reply is not None:
            return
        self.status_changed.emit("checking", self._health_url)
        request = QNetworkRequest(QUrl(self._health_url))
        request.setTransferTimeout(self._timeout_ms)
        reply = self._network.get(request)
        self._active_reply = reply
        reply.finished.connect(lambda checked_reply=reply: self._finish_check(checked_reply))

    def _finish_check(self, reply: QNetworkReply) -> None:
        if reply is not self._active_reply:
            reply.deleteLater()
            return
        self._active_reply = None
        status_code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if (
            reply.error() == QNetworkReply.NetworkError.NoError
            and status_code is not None
            and 200 <= int(status_code) < 400
        ):
            self.status_changed.emit("connected", self._health_url)
        else:
            detail = reply.errorString().strip() or "GPT-SoVITS API 没有响应"
            self.status_changed.emit("disconnected", detail)
        reply.deleteLater()
