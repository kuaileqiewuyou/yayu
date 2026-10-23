"""A manual background picker with an explicit transparent-background choice."""
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
)

from core.runtime.manual_background import background_file
from ui.frameless_dialog import build_frameless_dialog_shell
from ui.resources import set_button_icon
from ui.settings_ui.daylight import settings_qss
from ui.settings_ui.image_preview import image_preview

_PATH = Qt.ItemDataRole.UserRole
_READABLE = Qt.ItemDataRole.UserRole.value + 1


def _transparent_preview():
    pixmap = QPixmap(112, 70)
    pixmap.fill(QColor("#F7F8F3"))
    painter = QPainter(pixmap)
    for y in range(0, 70, 10):
        for x in range(0, 112, 10):
            if (x // 10 + y // 10) % 2:
                painter.fillRect(x, y, 10, 10, QColor("#DFE5DB"))
    painter.end()
    return pixmap


class BackgroundPicker(QDialog):
    apply_requested = Signal(str)
    manage_requested = Signal()

    def __init__(self, entries, current_path, parent=None):
        super().__init__(parent)
        content = build_frameless_dialog_shell(
            self, "切换背景", close_object_name="close_background_picker",
            close_accessible_name="Close background picker", close_tool_tip="关闭背景选择",
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAccessibleName("Choose chat background")
        self.resize(570, 440)
        self.setMinimumSize(440, 360)
        self.setStyleSheet(settings_qss() + """
            QDialog#frameless_session_dialog { background: transparent; }
            QListWidget#background_choices::item { padding: 6px; margin: 3px; }
            QLabel[role="error"] { color: #AD514A; }
        """)
        content.parentWidget().setStyleSheet(settings_qss())
        self.findChild(QLabel, "frameless_dialog_title").setText("切换背景")
        set_button_icon(self.findChild(QPushButton, "close_background_picker"), "close")
        hint = QLabel("选择背景图片，或使用无背景。")
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        content.addWidget(hint)
        self.choices = QListWidget()
        self.choices.setObjectName("background_choices")
        self.choices.setAccessibleName("Available backgrounds")
        self.choices.setViewMode(QListWidget.ViewMode.IconMode)
        self.choices.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.choices.setMovement(QListWidget.Movement.Static)
        self.choices.setIconSize(QSize(112, 70))
        self.choices.setGridSize(QSize(164, 126))
        self.choices.setWordWrap(True)
        self.choices.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        no_background = QListWidgetItem(QIcon(_transparent_preview()), "无背景")
        no_background.setData(_PATH, "")
        no_background.setData(_READABLE, True)
        no_background.setToolTip("恢复透明背景")
        self.choices.addItem(no_background)
        paths = {entry["path"] for entry in entries}
        if current_path and current_path not in paths:
            entries = [*entries, {"path": current_path, "label": Path(current_path).stem}]
        current_row = 0
        for entry in entries:
            preview = image_preview(str(background_file(entry["path"])), QSize(112, 70))
            readable = not preview.isNull()
            label = entry["label"] or Path(entry["path"]).stem
            item = QListWidgetItem(QIcon(preview), label if readable else f"{label}\n图片不可用")
            item.setData(_PATH, entry["path"])
            item.setData(_READABLE, readable)
            item.setToolTip(f"{label}\n{entry['path']}")
            self.choices.addItem(item)
            if entry["path"] == current_path:
                current_row = self.choices.count() - 1
        content.addWidget(self.choices, 1)
        self.error_label = QLabel()
        self.error_label.setProperty("role", "error")
        self.error_label.setStyleSheet("color: #AD514A; background: transparent;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        content.addWidget(self.error_label)
        actions = QHBoxLayout()
        self.manage_button = QPushButton("管理背景")
        self.manage_button.setObjectName("manage_backgrounds_button")
        self.manage_button.clicked.connect(self._manage)
        actions.addWidget(self.manage_button)
        actions.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        self.apply_button = QPushButton("应用背景")
        self.apply_button.setObjectName("apply_background_button")
        self.apply_button.setProperty("role", "primary")
        self.apply_button.clicked.connect(self._apply)
        actions.addWidget(self.apply_button)
        content.addLayout(actions)
        self.choices.currentItemChanged.connect(self._selection_changed)
        self.choices.itemDoubleClicked.connect(lambda *_: self._apply())
        self.choices.setCurrentRow(current_row)

    @property
    def selected_path(self):
        item = self.choices.currentItem()
        return item.data(_PATH) if item is not None else ""

    def _selection_changed(self, item, _previous):
        self.apply_button.setEnabled(bool(item is not None and item.data(_READABLE)))
        self.error_label.hide()

    def _apply(self):
        if self.apply_button.isEnabled():
            self.apply_requested.emit(self.selected_path)

    def _manage(self):
        self.reject()
        self.manage_requested.emit()

    def show_error(self, text):
        self.error_label.setText(text)
        self.error_label.show()
