import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.chat_ui.chat_ui import ChatUIWindow


class FakeApiController:
    def __init__(self, *, running=False):
        self.running = running
        self.start_calls = 0
        self.stop_calls = 0
        self.shutdown_calls = 0

    def is_running(self):
        return self.running

    def start(self):
        self.start_calls += 1
        self.running = True

    def stop(self):
        self.stop_calls += 1
        self.running = False

    def shutdown(self):
        self.shutdown_calls += 1
        self.running = False


def make_window():
    QApplication.instance() or QApplication([])
    return ChatUIWindow()


def test_api_toggle_is_exposed_beside_connection_status():
    window = make_window()
    try:
        button = window.gpt_sovits_api_toggle_btn
        assert button.objectName() == "toggle_gpt_sovits_api_button"
        assert window.conversation_info_popup.isAncestorOf(button)
        assert button.text() == "启动 API"
        assert button.isEnabled() is False
    finally:
        window.close()


def test_api_toggle_starts_and_stops_only_managed_process():
    window = make_window()
    controller = FakeApiController()
    try:
        window._gpt_sovits_api_manageable = True
        window._gpt_sovits_api_controller = controller
        window._set_gpt_sovits_connection_status("disconnected", "not running")
        assert window.gpt_sovits_api_toggle_btn.text() == "启动 API"
        assert window.gpt_sovits_api_toggle_btn.isEnabled() is True

        window.gpt_sovits_api_toggle_btn.click()
        assert controller.start_calls == 1
        window._sync_gpt_sovits_api_toggle()
        assert window.gpt_sovits_api_toggle_btn.text() == "停止 API"

        window.gpt_sovits_api_toggle_btn.click()
        assert controller.stop_calls == 1
    finally:
        window._gpt_sovits_api_controller = None
        window.close()


def test_connected_external_api_is_displayed_but_cannot_be_killed():
    window = make_window()
    controller = FakeApiController(running=False)
    try:
        window._gpt_sovits_api_manageable = True
        window._gpt_sovits_api_controller = controller
        window._set_gpt_sovits_connection_status("connected", "http://127.0.0.1:9880/docs")
        assert window.gpt_sovits_api_toggle_btn.text() == "外部运行"
        assert window.gpt_sovits_api_toggle_btn.isEnabled() is False
        assert controller.stop_calls == 0
    finally:
        window._gpt_sovits_api_controller = None
        window.close()


def test_window_close_shuts_down_only_its_managed_process():
    window = make_window()
    controller = FakeApiController(running=True)
    window._gpt_sovits_api_controller = controller
    window.close()
    assert controller.shutdown_calls == 1
