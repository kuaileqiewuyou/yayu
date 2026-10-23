from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QPushButton,
    QComboBox, QListWidget,
)

from ui.settings_ui.presentation import page_layout
from ui.settings_ui.media_list import ResourceListWidget


class BackgroundChoice(QComboBox):
    """Select a file path, keeping the explicit no-background choice first."""

    def __init__(self, library, parent=None):
        super().__init__(parent)
        self.library = library
        self._external_path = ""
        self.setMinimumWidth(0)
        self.setObjectName("background_path_combo")
        self.setAccessibleName("Current background")
        self.refresh()
        library.bindingsChanged.connect(self.refresh)

    def set_current_background(self, path):
        path = str(path or "")
        paths = {entry["path"] for entry in self.library.named_entries()}
        self._external_path = path if path and path not in paths else ""
        self.refresh(path)

    def refresh(self, selected_path=None):
        current = str(self.currentData() or "") if selected_path is None else selected_path
        entries = self.library.named_entries()
        if self._external_path in {entry["path"] for entry in entries}:
            # Once imported into this draft, ordinary library removal applies.
            self._external_path = ""
        with QSignalBlocker(self):
            self.clear()
            self.addItem("无背景", "")
            for entry in entries:
                self.addItem(entry["label"], entry["path"])
                self.setItemData(self.count() - 1, entry["path"], Qt.ItemDataRole.ToolTipRole)
            if self._external_path and self.findData(self._external_path) < 0:
                self.addItem(Path(self._external_path).stem, self._external_path)
                self.setItemData(self.count() - 1, self._external_path, Qt.ItemDataRole.ToolTipRole)
            self.setCurrentIndex(max(0, self.findData(current)))


@dataclass
class BackgroundSettingsTabParts:
    widget: QWidget
    scene_list: QListWidget
    add_scene_button: QPushButton
    remove_scene_button: QPushButton
    background_path_combo: BackgroundChoice


def build_background_tab(owner) -> BackgroundSettingsTabParts:
    widget = QWidget()
    widget.setObjectName("background_tab")
    widget.setAccessibleName("Background settings tab")
    layout = page_layout(widget, "背景设置", "手动选择聊天背景，也可以随时切换为无背景。")

    scene_list = ResourceListWidget("scene")
    scene_list.setObjectName("scene_list")
    scene_list.setAccessibleName("Scene background list")

    current_group = QGroupBox("当前背景")
    current_layout = QVBoxLayout(current_group)
    background_path_combo = BackgroundChoice(scene_list, current_group)
    current_layout.addWidget(background_path_combo)
    hint = QLabel("选择后点击“保存配置”生效。聊天窗口中也可以直接切换。")
    hint.setWordWrap(True)
    hint.setProperty("role", "muted")
    current_layout.addWidget(hint)
    layout.addWidget(current_group)

    scene_group = QGroupBox("背景图库")
    scene_layout = QVBoxLayout(scene_group)
    scene_btn_layout = QHBoxLayout()
    add_scene_button = QPushButton("添加图片")
    add_scene_button.setObjectName("add_scene_button")
    add_scene_button.setAccessibleName("Add scene image")
    add_scene_button.clicked.connect(owner._add_scene)
    remove_scene_button = QPushButton("移除选中")
    remove_scene_button.setObjectName("remove_scene_button")
    remove_scene_button.setAccessibleName("Remove selected scene")
    remove_scene_button.clicked.connect(lambda: owner._remove_selected(scene_list))
    remove_scene_button.setEnabled(False)
    remove_scene_button.setProperty("role", "danger")
    scene_list.itemSelectionChanged.connect(
        lambda: remove_scene_button.setEnabled(bool(scene_list.selectedItems())))
    scene_btn_layout.addWidget(add_scene_button)
    scene_btn_layout.addWidget(remove_scene_button)
    scene_btn_layout.addStretch()
    scene_layout.addLayout(scene_btn_layout)
    scene_layout.addWidget(scene_list)
    layout.addWidget(scene_group)
    layout.addStretch()

    return BackgroundSettingsTabParts(
        widget, scene_list, add_scene_button, remove_scene_button, background_path_combo,
    )
