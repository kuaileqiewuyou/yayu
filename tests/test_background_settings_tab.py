import ast
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from ui.settings_ui.background_tab import build_background_tab


@pytest.fixture
def qapp(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


class FakeSettingsWindow:
    def __init__(self):
        self.scene_adds = 0
        self.bgm_adds = 0
        self.removed_lists = []

    def _add_scene(self):
        self.scene_adds += 1

    def _add_bgm(self):
        self.bgm_adds += 1

    def _remove_selected(self, list_widget):
        self.removed_lists.append(list_widget)


def test_background_tab_exposes_manual_choice_and_no_music_controls(qapp):
    owner = FakeSettingsWindow()
    parts = build_background_tab(owner)
    assert parts.widget.objectName() == "background_tab"
    assert parts.widget.accessibleName() == "Background settings tab"
    assert parts.scene_list.objectName() == "scene_list"
    assert parts.background_path_combo.currentText() == "无背景"
    assert parts.background_path_combo.currentData() == ""
    assert not hasattr(parts, "bgm_list")
    assert not hasattr(parts, "bg_tags_edit")
    assert not parts.remove_scene_button.isEnabled()
    parts.scene_list.set_named_entries([
        {"path": "room.png", "label": "书房"},
        {"path": "park.png", "label": "公园"},
    ])
    assert [parts.background_path_combo.itemText(i) for i in range(3)] == ["无背景", "书房", "公园"]
    parts.scene_list.setCurrentRow(0)
    parts.add_scene_button.click()
    parts.remove_scene_button.click()
    assert owner.scene_adds == 1
    assert owner.removed_lists == [parts.scene_list]
    parts.widget.deleteLater()


def test_choice_keeps_paths_when_names_change_and_clears_removed_choice(qapp):
    parts = build_background_tab(FakeSettingsWindow())
    parts.scene_list.set_named_entries([
        {"path": "room.png", "label": "书房"},
        {"path": "park.png", "label": "公园"},
    ])
    parts.background_path_combo.set_current_background("park.png")
    editor = parts.scene_list.itemWidget(parts.scene_list.item(1)).name_edit
    editor.setText("夜晚公园")
    assert parts.background_path_combo.currentText() == "夜晚公园"
    assert parts.background_path_combo.currentData() == "park.png"
    parts.scene_list.takeItem(1)
    assert parts.background_path_combo.currentText() == "无背景"
    assert parts.background_path_combo.currentData() == ""
    parts.widget.deleteLater()


def test_settings_window_background_tab_method_delegates_to_builder_without_inline_widget_ownership():
    window_path = Path(__file__).resolve().parents[1] / "ui" / "settings_ui" / "window.py"
    source = window_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    settings_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SettingsWindow")
    method = next(
        node
        for node in settings_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "_create_background_tab"
    )
    method_source = ast.get_source_segment(source, method)

    assert "build_background_tab(self)" in method_source
    assert "self.scene_list = self._background_tab_parts.scene_list" in method_source
    assert "self.add_scene_button = self._background_tab_parts.add_scene_button" in method_source
    assert "self.background_path_combo = self._background_tab_parts.background_path_combo" in method_source
    assert "bgm" not in method_source
    assert "QGroupBox(" not in method_source
    assert "QListWidget()" not in method_source
    assert "QLineEdit()" not in method_source
    assert "layout.addWidget" not in method_source
