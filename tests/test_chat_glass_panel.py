import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui.chat_ui.chat_ui import ChatUIWindow
from ui.theme import CHAT_DIALOGUE_GLASS_STYLE, CHAT_TEMPORARY_CONTENT_GLASS_STYLE, CHAT_TEMPORARY_CONTENT_STYLE


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_chat_history_uses_named_semitransparent_glass_style(app):
    window = ChatUIWindow()
    try:
        assert window.temporary_content_scroll_area.styleSheet() == CHAT_TEMPORARY_CONTENT_GLASS_STYLE
        assert "rgba(247, 248, 243, 219)" in CHAT_DIALOGUE_GLASS_STYLE
        assert "border-radius: 16px" in CHAT_TEMPORARY_CONTENT_GLASS_STYLE
        assert "rgba(116, 137, 118, 46)" in CHAT_TEMPORARY_CONTENT_GLASS_STYLE
    finally:
        window.close()


def test_chat_history_content_paints_the_semitransparent_glass_fill(app):
    window = ChatUIWindow()
    try:
        assert window.temporary_content_scroll_area.viewport().autoFillBackground() is False
        assert window.temporary_content_widget.styleSheet() == CHAT_TEMPORARY_CONTENT_STYLE
    finally:
        window.close()


def test_chat_history_glass_background_is_actually_painted(app):
    window = ChatUIWindow()
    try:
        window.show()
        app.processEvents()
        image = window.grab().toImage()
        sample = window.temporary_content_widget.mapTo(window, window.temporary_content_widget.rect().center())
        assert image.pixelColor(sample).alpha() > 0
    finally:
        window.close()
