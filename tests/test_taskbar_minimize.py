import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from config.config_manager import ConfigManager
from ui.chat_ui.chat_ui import ChatUIWindow
from ui.settings_ui.window import SettingsWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def reset_config_manager():
    ConfigManager.reset()
    yield
    ConfigManager.reset()


@pytest.mark.parametrize("window_factory", [ChatUIWindow, SettingsWindow])
def test_frameless_windows_keep_native_taskbar_minimize_capability(app, window_factory) -> None:
    window = window_factory()
    try:
        flags = window.windowFlags()
        assert flags & Qt.WindowType.FramelessWindowHint
        assert flags & Qt.WindowType.WindowSystemMenuHint
        assert flags & Qt.WindowType.WindowMinimizeButtonHint
    finally:
        window.close()


def test_main_window_can_round_trip_through_minimized_state(app) -> None:
    window = ChatUIWindow()
    window.show()
    app.processEvents()
    try:
        window.showMinimized()
        app.processEvents()
        assert window.isMinimized()

        window.showNormal()
        app.processEvents()
        assert not window.isMinimized()
    finally:
        window.close()
