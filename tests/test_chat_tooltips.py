"""Tooltips must keep an opaque fill inside the transparent chat window."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtGui import QColor, QHelpEvent, QImage, QPalette
from PySide6.QtWidgets import QApplication, QPushButton, QToolTip

from ui.chat_ui.chat_ui import ChatUIWindow
from ui.theme import dialogs_qss


@pytest.fixture(scope="module")
def app():
    # Qt keeps a shared tooltip window; keep its QApplication alive across cases.
    return QApplication.instance() or QApplication([])


def _luminance(color):
    channels = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
                for value in (color.redF(), color.greenF(), color.blueF())]
    return sum(weight * value for weight, value in zip((0.2126, 0.7152, 0.0722), channels))


@pytest.mark.parametrize("background", ["initial", "image", "cleared", "missing"])
def test_chat_tooltips_remain_readable_after_background_changes(app, background, tmp_path):
    old_style = app.styleSheet()
    app.setStyleSheet(dialogs_qss())
    window = ChatUIWindow()
    try:
        if background != "initial":
            path = tmp_path / "chat background.png"
            image = QImage(40, 40, QImage.Format.Format_RGB32)
            image.fill(QColor("#102030"))
            assert image.save(str(path))
            window.set_background(str(path))
            if background == "cleared":
                window.set_background("")
            elif background == "missing":
                window.set_background(str(tmp_path / "missing.png"))
        window.show()
        app.processEvents()
        for name in ("history_button", "background_button", "settings_button", "minimize_button", "close_button",
                     "dialog_next_indicator", "action_menu_button", "companion_toggle_button"):
            button = window.findChild(QPushButton, name)
            assert button is not None and button.toolTip(), name
            position = button.rect().center()
            event = QHelpEvent(QEvent.Type.ToolTip, position, button.mapToGlobal(position))
            assert QApplication.sendEvent(button, event), name
            app.processEvents()
            tooltip = next(widget for widget in app.topLevelWidgets()
                           if widget.objectName() == "qtooltip_label" and widget.isVisible())
            assert tooltip.text() == button.toolTip(), name
            rendered = tooltip.grab().toImage()
            fill = rendered.pixelColor(10, rendered.height() // 2)
            assert fill.alpha() == 255, name
            assert min(fill.red(), fill.green(), fill.blue()) >= 240, name
            text = tooltip.palette().color(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipText)
            assert (_luminance(fill) + 0.05) / (_luminance(text) + 0.05) >= 7, name
        # Keep the stage transparent after restricting its styles to named containers.
        if background in ("initial", "cleared"):
            stage = window.grab().toImage()
            assert stage.pixelColor(20, 100).alpha() == 0
    finally:
        QToolTip.hideText()
        window.close()
        window.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        app.setStyleSheet(old_style)
