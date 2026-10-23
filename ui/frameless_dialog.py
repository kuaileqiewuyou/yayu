"""Reusable project-drawn chrome for small modal dialogs."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.theme import CHAT_ICON_BTN_CLOSE, HISTORY_PANEL_STYLE, HISTORY_TITLE_STYLE
from ui.window_chrome import WindowDragController


def build_frameless_dialog_shell(
    dialog: QDialog,
    title: str,
    *,
    close_object_name: str,
    close_accessible_name: str,
    close_tool_tip: str,
) -> QVBoxLayout:
    """Apply the chat-history visual language and return the panel content layout."""
    dialog.setObjectName("frameless_session_dialog")
    dialog.setWindowTitle(title)
    dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
    dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    dialog.setStyleSheet("QDialog#frameless_session_dialog { background: transparent; }")

    outer = QVBoxLayout(dialog)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    panel = QFrame(dialog)
    panel.setObjectName("frameless_dialog_panel")
    panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    panel.setStyleSheet(HISTORY_PANEL_STYLE.replace("#history_panel", "#frameless_dialog_panel"))
    panel_layout = QVBoxLayout(panel)
    panel_layout.setContentsMargins(0, 0, 0, 0)
    panel_layout.setSpacing(0)
    outer.addWidget(panel)

    titlebar = QWidget(panel)
    titlebar.setObjectName("frameless_dialog_titlebar")
    titlebar.setStyleSheet(
        "QWidget#frameless_dialog_titlebar { background-color: rgba(116, 137, 118, 13); "
        "border-bottom: 1px solid rgba(116, 137, 118, 46); }"
    )
    titlebar_layout = QHBoxLayout(titlebar)
    titlebar_layout.setContentsMargins(16, 10, 10, 10)
    titlebar_layout.setSpacing(10)

    title_label = QLabel(f"❀ {title}", titlebar)
    title_label.setObjectName("frameless_dialog_title")
    title_label.setStyleSheet(HISTORY_TITLE_STYLE)
    titlebar_layout.addWidget(title_label)
    titlebar_layout.addStretch()

    close_button = QPushButton("✕", titlebar)
    close_button.setObjectName(close_object_name)
    close_button.setAccessibleName(close_accessible_name)
    close_button.setToolTip(close_tool_tip)
    close_button.setFixedSize(32, 32)
    close_button.setCursor(Qt.CursorShape.PointingHandCursor)
    close_button.setStyleSheet(CHAT_ICON_BTN_CLOSE)
    close_button.clicked.connect(dialog.reject)
    titlebar_layout.addWidget(close_button)
    panel_layout.addWidget(titlebar)

    content = QWidget(panel)
    content.setObjectName("frameless_dialog_content")
    content_layout = QVBoxLayout(content)
    content_layout.setContentsMargins(16, 14, 16, 16)
    content_layout.setSpacing(10)
    panel_layout.addWidget(content)
    dialog._window_drag_controller = WindowDragController(dialog, [titlebar, title_label])
    return content_layout
