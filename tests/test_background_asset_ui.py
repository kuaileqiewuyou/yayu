"""Real Qt coverage for names bound to files, persistence and failed saves."""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import yaml
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QImage, QImageReader, QInputMethodEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from config.config_manager import ConfigManager
from core.security.allowed_roots import AllowedRootsStore
from ui.settings_ui.window import SettingsWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in ("API_CONFIG", "API_LOCAL_CONFIG", "SYSTEM_CONFIG", "CHARACTERS_CONFIG", "BACKGROUND_CONFIG", "MCP_CONFIG"):
        monkeypatch.setattr(ConfigManager, f"_{name}_PATH", tmp_path / f"{name.lower()}.yaml")
    ConfigManager._CHARACTERS_CONFIG_PATH.write_text(yaml.safe_dump([
        {"name": "测试角色", "character_setting": "友善的对话伙伴", "emotion_tags": "0: neutral"},
    ], allow_unicode=True), encoding="utf-8")
    ConfigManager._BACKGROUND_CONFIG_PATH.write_text(yaml.safe_dump([{
        "name": "旧场景组", "sprites": [{"path": "class.png"}, {"path": "park.png"}],
        "bg_tags": "1-教室 2-夜晚 公园 3-没有对应图片",
        "bgm_list": ["calm.ogg"], "bgm_tags": "1-平静 日常 2-没有对应音乐",
    }], allow_unicode=True), encoding="utf-8")
    source_dir = tmp_path / "data/backgrounds"
    source_dir.mkdir(parents=True)
    for filename in ("class.png", "park.png", "new garden.png", "outside.png"):
        image = QImage(160, 100, QImage.Format.Format_RGB32)
        image.fill(0xff819b78)
        assert image.save(str(source_dir / filename))
    ConfigManager.reset()
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **kw: None)
    w = SettingsWindow(allowed_roots_store=AllowedRootsStore(tmp_path / "roots.json", project_root=tmp_path))
    w.template_sample_output_edit.setPlainText(json.dumps({
        "character_name": "测试角色", "speech": "你好", "sprite": "0",
    }, ensure_ascii=False))
    w._settings_dirty = False
    yield w
    w._settings_dirty = False
    w.close()
    w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    ConfigManager.reset()


def edit_name(widget, index, text):
    editor = widget.itemWidget(widget.item(index)).name_edit
    editor.setFocus()
    editor.selectAll()
    event = QInputMethodEvent()
    event.setCommitString(text)
    QApplication.sendEvent(editor, event)
    return editor


def test_legacy_names_appear_beside_files_without_music_ui(window):
    assert window.scene_list.named_entries() == [
        {"path": "class.png", "label": "教室"}, {"path": "park.png", "label": "夜晚 公园"},
    ]
    assert window.scene_list.itemWidget(window.scene_list.item(1)).name_edit.text() == "夜晚 公园"
    assert window.background_path_combo.currentText() == "无背景"
    assert window.background_path_combo.currentData() == ""
    assert not hasattr(window, "bgm_list")
    assert not hasattr(window, "bg_tags_edit")
    assert window.settings_tabs.tabText(2) == "背景设置"
    assert not window._settings_dirty


def test_edit_delete_and_save_reload_keep_names_with_files_and_manual_choice(window):
    emitted = []
    window.background_changed.connect(emitted.append)
    edit_name(window.scene_list, 1, "雨后 公园 🌿")
    window.background_path_combo.setCurrentIndex(2)
    window.scene_list.setCurrentRow(0)
    window.remove_scene_button.click()
    assert window.background_path_combo.currentData() == "park.png"
    row = window.scene_list.itemWidget(window.scene_list.item(0))
    assert row.number.text() == "01"
    assert row.name_edit.text() == "雨后 公园 🌿"
    window._save_config()
    assert not window._settings_dirty
    assert emitted == ["park.png"]
    stored = yaml.safe_load(ConfigManager._BACKGROUND_CONFIG_PATH.read_text(encoding="utf-8"))[0]
    assert [item["path"] for item in stored["sprites"]] == ["park.png"]
    assert stored["scene_bindings"] == [{"path": "park.png", "label": "雨后 公园 🌿"}]
    assert stored["bgm_list"] == ["calm.ogg"]  # inert legacy data, no controls
    assert yaml.safe_load(ConfigManager._SYSTEM_CONFIG_PATH.read_text(encoding="utf-8"))["background_path"] == "park.png"
    ConfigManager.reset()
    window.config = ConfigManager()
    window._load_config()
    assert window.scene_list.named_entries() == [{"path": "park.png", "label": "雨后 公园 🌿"}]
    assert window.background_path_combo.currentData() == "park.png"
    assert not window._settings_dirty


def test_adding_files_creates_editors_that_still_mark_unsaved_changes(window, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **kw: (["new garden.png"], ""))
    window.add_scene_button.click()
    assert window.scene_list.named_entries()[-1] == {"path": "new garden.png", "label": "new garden"}
    assert window.background_path_combo.itemData(3) == "new garden.png"
    window._settings_dirty = False
    edit_name(window.scene_list, 2, "春天 花园")
    assert window._settings_dirty
    assert window.background_path_combo.itemText(3) == "春天 花园"


def test_failed_save_keeps_names_choice_and_disk_contents_and_emits_nothing(window, monkeypatch):
    before = ConfigManager._BACKGROUND_CONFIG_PATH.read_bytes()
    emitted = []
    window.background_changed.connect(emitted.append)
    window.settings_nav.setCurrentRow(2)
    window.scene_list.setCurrentRow(1)
    edit_name(window.scene_list, 1, "雨后 公园")
    window.background_path_combo.setCurrentIndex(2)

    def fail():
        raise OSError("simulated background write failure")

    monkeypatch.setattr(window.config, "save_backgrounds", fail)
    window._save_config()
    assert "失败" in window.save_status_label.text()
    assert window._settings_dirty
    assert window.settings_tabs.currentIndex() == 2
    assert window.scene_list.currentRow() == 1
    assert window.scene_list.named_entries()[1]["label"] == "雨后 公园"
    assert window.background_path_combo.currentData() == "park.png"
    assert window.config.system_config.background_path == ""
    assert ConfigManager._BACKGROUND_CONFIG_PATH.read_bytes() == before
    assert emitted == []


def test_remove_selected_current_background_defaults_to_no_background_and_saves(window):
    window.set_current_background("park.png")
    window.scene_list.setCurrentRow(1)
    window.remove_scene_button.click()
    assert window.background_path_combo.currentText() == "无背景"
    assert window.background_path_combo.currentData() == ""
    window._save_config()
    assert not window._settings_dirty
    assert window.config.system_config.background_path == ""


def test_remove_all_keeps_explicit_no_background_available(window):
    while window.scene_list.count():
        window.scene_list.setCurrentRow(0)
        window._remove_selected(window.scene_list)
    assert not window.scene_list._empty.isHidden()
    assert not window.remove_scene_button.isEnabled()
    assert window.background_path_combo.count() == 1
    assert window.background_path_combo.currentText() == "无背景"
    window._save_config()
    assert not window._settings_dirty
    assert window.config.system_config.background_path == ""


def test_chat_sync_preserves_path_outside_draft_and_does_not_mark_dirty(window):
    window.set_current_background("outside.png")
    assert not window._settings_dirty
    assert window.background_path_combo.currentData() == "outside.png"
    edit_name(window.scene_list, 0, "新名称")
    assert window.background_path_combo.currentData() == "outside.png"
    window._save_config()
    assert window.config.system_config.background_path == "outside.png"
    window.set_current_background("")
    assert not window._settings_dirty
    window._save_config()
    assert window.config.system_config.background_path == ""


def test_unreadable_background_does_not_persist_or_emit(window):
    emitted = []
    window.background_changed.connect(emitted.append)
    window.set_current_background("missing.png")
    window._settings_dirty = True
    before = ConfigManager._BACKGROUND_CONFIG_PATH.read_bytes()
    window._save_config()
    assert "背景图片无法读取" in window.save_status_label.text()
    assert window._settings_dirty
    assert window.background_path_combo.currentData() == "missing.png"
    assert window.config.system_config.background_path == ""
    assert ConfigManager._BACKGROUND_CONFIG_PATH.read_bytes() == before
    assert emitted == []


def test_synced_external_background_becomes_removable_after_import(window):
    window.set_current_background("outside.png")
    window.scene_list.addItem("outside.png")
    assert window.background_path_combo.currentData() == "outside.png"
    window.scene_list.takeItem(2)
    assert window.background_path_combo.currentData() == ""
    assert window.background_path_combo.currentText() == "无背景"


def test_png_header_without_decodable_pixels_cannot_be_saved(window, tmp_path):
    source = tmp_path / "data/backgrounds/class.png"
    broken = tmp_path / "data/backgrounds/broken.png"
    broken.write_bytes(source.read_bytes()[:50])
    assert QImageReader(str(broken)).canRead()
    emitted = []
    window.background_changed.connect(emitted.append)
    window.set_current_background("broken.png")
    window._settings_dirty = True
    window._save_config()
    assert "背景图片无法读取" in window.save_status_label.text()
    assert window.config.system_config.background_path == ""
    assert window._settings_dirty
    assert emitted == []


def test_names_and_manual_choice_fit_normal_and_compact_windows(window, app):
    window.settings_nav.setCurrentRow(2)
    window._page_transition.finish()
    window.show()
    for width, height in ((1280, 900), (800, 650), (1280, 900)):
        window.resize(width, height)
        app.processEvents()
        app.processEvents()
        view = window.scene_list
        row = view.itemWidget(view.item(0))
        assert view.viewport().rect().contains(row.geometry())
        assert row.rect().contains(row.name_edit.geometry())
        assert row.name_edit.width() > 100
        assert window.background_path_combo.width() > 200
    window.scene_list.clearSelection()
    row = window.scene_list.itemWidget(window.scene_list.item(1))
    QTest.mouseClick(row.name_edit, Qt.MouseButton.LeftButton)
    assert window.scene_list.currentRow() == 1
    assert window.remove_scene_button.isEnabled()
    assert not window._settings_dirty
