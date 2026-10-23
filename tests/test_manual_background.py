"""Real Qt end-to-end checks of explicit background and no-background choices."""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import yaml
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QImage
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QMessageBox

from config.config_manager import ConfigManager
from core.runtime.lazy_settings import LazySettingsWindow
from core.runtime.manual_background import ManualBackgroundController
from core.security.allowed_roots import AllowedRootsStore
from ui.chat_ui.chat_ui import ChatUIWindow
from ui.settings_ui.window import SettingsWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def context(app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in ("API_CONFIG", "API_LOCAL_CONFIG", "SYSTEM_CONFIG", "CHARACTERS_CONFIG", "BACKGROUND_CONFIG", "MCP_CONFIG"):
        monkeypatch.setattr(ConfigManager, f"_{name}_PATH", tmp_path / f"{name.lower()}.yaml")
    image = QImage(100, 80, QImage.Format.Format_RGB32)
    image.fill(0x607B65)
    first, second = tmp_path / "park.png", tmp_path / "room.png"
    image.save(str(first))
    image.fill(0xD4CCB1)
    image.save(str(second))
    ConfigManager._CHARACTERS_CONFIG_PATH.write_text(yaml.safe_dump([
        {"name": "测试角色", "character_setting": "友善的对话伙伴", "emotion_tags": "0: neutral"},
    ], allow_unicode=True), encoding="utf-8")
    ConfigManager._BACKGROUND_CONFIG_PATH.write_text(yaml.safe_dump([{
        "name": "场景组", "sprites": [{"path": str(first)}, {"path": str(second)}],
        "bg_tags": "1-公园 2-家中", "bgm_list": ["retired.ogg"], "bgm_tags": "1-旧音乐",
    }], allow_unicode=True), encoding="utf-8")
    ConfigManager.reset()
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **kw: None)
    config = ConfigManager()
    chat = ChatUIWindow()

    def make_settings():
        window = SettingsWindow(allowed_roots_store=AllowedRootsStore(tmp_path / "roots.json", project_root=tmp_path))
        window.template_sample_output_edit.setPlainText(json.dumps({
            "character_name": "测试角色", "speech": "你好", "sprite": "0",
        }, ensure_ascii=False))
        window._settings_dirty = False
        return window

    lazy = LazySettingsWindow(make_settings)
    controller = ManualBackgroundController(chat, config, lazy)
    controller.restore()
    chat.show()
    app.processEvents()
    yield chat, controller, lazy, first, second
    if lazy.is_created:
        lazy._window._settings_dirty = False
        lazy._window.close()
        lazy._window.deleteLater()
    if controller._picker is not None:
        controller._picker.reject()
    chat.close()
    chat.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    ConfigManager.reset()


def open_picker(chat, controller, app):
    chat.background_btn.click()
    app.processEvents()
    return controller._picker


def test_default_is_no_background_even_with_existing_library(context, app):
    chat, controller, lazy, first, _ = context
    assert controller.current_path == ""
    assert chat.centralWidget().background_path == ""
    picker = open_picker(chat, controller, app)
    assert picker.choices.item(0).text() == "无背景"
    assert picker.selected_path == ""
    assert picker.apply_button.isEnabled()
    assert not lazy.is_created
    picker.reject()


def test_empty_library_keeps_no_background_and_manage_opens_background_settings(context, app):
    chat, controller, lazy, first, _ = context
    controller.config.config.backgrounds = []
    picker = open_picker(chat, controller, app)
    assert picker.choices.count() == 1
    assert picker.choices.item(0).text() == "无背景"
    assert picker.apply_button.isEnabled()
    picker.manage_button.click()
    assert not picker.isVisible()
    assert lazy.is_created
    assert lazy._window.settings_tabs.currentIndex() == 2
    assert lazy._window.background_path_combo.currentData() == ""


def test_real_chat_button_applies_and_persists_without_sending_a_model_turn(context, app):
    chat, controller, lazy, first, _ = context
    sent = QSignalSpy(chat.user_message_sent)
    picker = open_picker(chat, controller, app)
    picker.choices.setCurrentRow(1)
    picker.apply_button.click()
    assert not picker.isVisible()
    assert controller.current_path == str(first)
    assert chat.centralWidget().background_path == str(first)
    assert chat.grab().toImage().pixelColor(400, 200).alpha() == 255
    assert yaml.safe_load(ConfigManager._SYSTEM_CONFIG_PATH.read_text(encoding="utf-8"))["background_path"] == str(first)
    assert sent.count() == 0
    assert not lazy.is_created


def test_no_background_clears_image_and_survives_reload(context, app):
    chat, controller, lazy, first, _ = context
    assert controller.select_background(str(first))
    picker = open_picker(chat, controller, app)
    picker.choices.setCurrentRow(0)
    picker.apply_button.click()
    assert controller.current_path == ""
    assert chat.centralWidget().background_path == ""
    assert chat.grab().toImage().pixelColor(400, 200).alpha() == 0
    assert yaml.safe_load(ConfigManager._SYSTEM_CONFIG_PATH.read_text(encoding="utf-8"))["background_path"] == ""
    ConfigManager.reset()
    controller.config = ConfigManager()
    controller.restore()
    assert controller.current_path == ""
    assert chat.centralWidget().background_path == ""


def test_cancel_does_not_apply_a_different_background(context, app):
    chat, controller, lazy, first, _ = context
    controller.select_background(str(first))
    before = ConfigManager._SYSTEM_CONFIG_PATH.read_bytes()
    picker = open_picker(chat, controller, app)
    picker.choices.setCurrentRow(0)
    picker.reject()
    assert controller.current_path == str(first)
    assert chat.centralWidget().background_path == str(first)
    assert ConfigManager._SYSTEM_CONFIG_PATH.read_bytes() == before


def test_failed_save_keeps_previous_picture_and_picker_choice_for_retry(context, app, monkeypatch):
    chat, controller, lazy, first, second = context
    controller.select_background(str(first))
    before = ConfigManager._SYSTEM_CONFIG_PATH.read_bytes()
    picker = open_picker(chat, controller, app)
    picker.choices.setCurrentRow(2)

    def fail():
        raise OSError("simulated write failure")

    monkeypatch.setattr(controller.config, "save_system_config", fail)
    picker.apply_button.click()
    assert picker.isVisible()
    assert picker.selected_path == str(second)
    assert not picker.error_label.isHidden()
    assert controller.current_path == controller.config.system_config.background_path == str(first)
    assert chat.centralWidget().background_path == str(first)
    assert ConfigManager._SYSTEM_CONFIG_PATH.read_bytes() == before


def test_unreadable_picture_never_overwrites_a_good_choice(context, app):
    chat, controller, lazy, first, second = context
    controller.select_background(str(first))
    second.write_text("not an image", encoding="utf-8")
    picker = open_picker(chat, controller, app)
    picker.choices.setCurrentRow(2)
    assert not picker.apply_button.isEnabled()
    assert not controller.select_background(str(second))
    assert controller.current_path == str(first)
    picker.choices.setCurrentRow(0)
    assert picker.apply_button.isEnabled()


def test_truncated_png_cannot_replace_or_restore_a_good_image(context, app):
    chat, controller, lazy, first, second = context
    controller.select_background(str(first))
    second.write_bytes(second.read_bytes()[:50])
    assert not controller.select_background(str(second))
    assert controller.current_path == str(first)
    controller.config.system_config.background_path = str(second)
    controller.restore()
    assert controller.current_path == ""
    assert chat.centralWidget().background_path == ""


def test_settings_and_chat_choices_sync_live_without_overwriting_other_drafts(context, app):
    chat, controller, lazy, first, second = context
    lazy.show_background_settings()
    window = lazy._window
    assert window.background_path_combo.itemText(0) == "无背景"
    index = window.background_path_combo.findData(str(first))
    window.background_path_combo.setCurrentIndex(index)
    window._save_config()
    assert not window._settings_dirty
    assert controller.current_path == str(first)
    window.char_name_edit.setText("未保存的人物名称")
    window._settings_dirty = True
    controller.select_background(str(second))
    assert window.background_path_combo.currentData() == str(second)
    assert window.char_name_edit.text() == "未保存的人物名称"
    assert window._settings_dirty
    window._save_config()
    assert not window._settings_dirty
    assert controller.current_path == str(second)
    window.background_path_combo.setCurrentIndex(0)
    window._save_config()
    assert controller.current_path == ""
    assert chat.centralWidget().background_path == ""
