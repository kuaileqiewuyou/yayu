import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from tts.connection_monitor import GPTSoVITSConnectionMonitor
from ui.chat_ui.chat_ui import ChatUIWindow


def app():
    return QApplication.instance() or QApplication([])


def test_configuring_monitor_does_not_start_background_requests():
    app()
    monitor = GPTSoVITSConnectionMonitor(timeout_ms=100)
    spy = QSignalSpy(monitor.status_changed)

    monitor.configure("http://127.0.0.1:9880")

    assert spy.count() == 0
    assert not hasattr(monitor, "_timer")


def test_manual_check_emits_checking_immediately():
    app()
    monitor = GPTSoVITSConnectionMonitor(timeout_ms=100)
    spy = QSignalSpy(monitor.status_changed)
    monitor.configure("http://127.0.0.1:9880")

    monitor.check_now()

    assert spy.count() >= 1
    assert spy.at(0)[0] == "checking"
    monitor.stop()


def test_window_stays_unchecked_until_popup_or_refresh():
    app()
    window = ChatUIWindow()
    try:
        window.configure_tts_connection_status("gpt-sovits", "http://127.0.0.1:9880")
        assert window.gpt_sovits_status_label.text() == "GPT-SoVITS：未检查"
        assert window._gpt_sovits_startup_probe_timer.isActive() is False

        window.refresh_gpt_sovits_connection_status()
        assert window.gpt_sovits_status_label.text() == "GPT-SoVITS：◌ 检查中…"
    finally:
        window.close()


def test_temporary_polling_runs_only_while_managed_api_starts():
    app()
    window = ChatUIWindow()
    try:
        window._on_gpt_sovits_api_process_state("running", "loading")
        assert window._gpt_sovits_startup_probe_timer.isActive() is True

        window._set_gpt_sovits_connection_status("connected", "ready")
        assert window._gpt_sovits_startup_probe_timer.isActive() is False
    finally:
        window.close()
