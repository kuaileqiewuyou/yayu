"""Real Qt character selectors with isolated authored config and no model calls."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import yaml
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from config.config_manager import ConfigManager
from core.runtime.lazy_settings import LazySettingsWindow
from core.security.allowed_roots import AllowedRootsStore
from ui.chat_ui.chat_ui import ChatUIWindow
from ui.settings_ui.window import SettingsWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings(app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in ("API_CONFIG", "API_LOCAL_CONFIG", "SYSTEM_CONFIG", "CHARACTERS_CONFIG", "BACKGROUND_CONFIG", "MCP_CONFIG"):
        monkeypatch.setattr(ConfigManager, f"_{name}_PATH", tmp_path / f"{name.lower()}.yaml")
    ConfigManager._CHARACTERS_CONFIG_PATH.write_text(yaml.safe_dump([
        {"name": "同名角色", "memory_id": "character-a", "character_setting": "A的设定"},
        {"name": "同名角色", "memory_id": "character-b", "character_setting": "B的设定"},
    ], allow_unicode=True), encoding="utf-8")
    ConfigManager._SYSTEM_CONFIG_PATH.write_text("active_character_id: character-a\n", encoding="utf-8")
    ConfigManager.reset()
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
    window = SettingsWindow(allowed_roots_store=AllowedRootsStore(tmp_path / "roots.json", project_root=tmp_path))
    # The save transaction is real; the separate template publication validator
    # is covered by its own tests and is irrelevant to choosing a chat partner.
    monkeypatch.setattr(window, "_build_template_preflight_report", lambda **kwargs: ("ok", "通过"))
    yield window
    window._settings_dirty = False
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    ConfigManager.reset()


@pytest.fixture
def chat(app):
    window = ChatUIWindow()
    window.set_character_list([
        {"id": "character-a", "name": "同名角色"},
        {"memory_id": "character-b", "name": "同名角色"},
    ], "character-a")
    window.show()
    app.processEvents()
    yield window
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def test_home_selector_uses_stable_ids_and_marks_current_character(chat, app):
    requested = QSignalSpy(chat.character_requested)
    QTest.mouseClick(chat.current_speaker_label, Qt.MouseButton.LeftButton)
    app.processEvents()
    actions = chat._character_menu.actions()
    assert [action.text() for action in actions] == ["同名角色", "同名角色"]
    assert [action.data() for action in actions] == ["character-a", "character-b"]
    assert [action.isChecked() for action in actions] == [True, False]
    actions[0].trigger()
    assert requested.count() == 0
    actions[1].trigger()
    assert requested.at(0) == ["character-b"]
    # The controller confirms a switch; the selector never assumes it succeeded.
    assert chat._active_character_id == "character-a"
    chat.set_character_list([
        {"memory_id": "character-b", "name": "改名后的B"},
        {"memory_id": "character-a", "name": "A"},
    ], "character-b")
    assert chat.current_speaker_label.text() == "改名后的B"
    chat._show_character_menu()
    assert [action.isChecked() for action in chat._character_menu.actions()] == [True, False]


def test_home_selector_remains_available_without_dialogue_and_supports_keyboard(chat, app):
    chat.clear_messages()
    assert chat.current_speaker_label.isVisible()
    assert chat.current_speaker_label.text() == "同名角色"
    assert chat.current_speaker_label.focusPolicy() == Qt.FocusPolicy.StrongFocus
    chat.current_speaker_label.setFocus()
    QTest.keyClick(chat.current_speaker_label, Qt.Key.Key_Return)
    app.processEvents()
    assert chat._character_menu.isVisible()


def test_opening_selector_refreshes_saved_roster_even_with_empty_cache(chat):
    roster = [{"id": "character-a", "name": "已保存角色A"}]
    opening = QSignalSpy(chat.character_menu_opening)
    chat._character_items = []
    chat.character_menu_opening.connect(lambda: chat.set_character_list(roster, "character-a"))
    chat._show_character_menu()
    assert opening.count() == 1
    assert [action.text() for action in chat._character_menu.actions()] == ["已保存角色A"]
    roster.append({"id": "new-character", "name": "新建并保存的角色"})
    chat._show_character_menu()
    assert opening.count() == 2
    assert [action.data() for action in chat._character_menu.actions()] == ["character-a", "new-character"]
    chat.set_waiting_for_reply(True)
    chat._show_character_menu()
    assert opening.count() == 2


def test_reply_blocks_even_previously_open_character_actions(chat, app):
    requested = QSignalSpy(chat.character_requested)
    waiting = QSignalSpy(chat.reply_waiting_changed)
    chat._show_character_menu()
    pending_action = chat._character_menu.actions()[1]
    chat.set_waiting_for_reply(True)
    assert not chat.current_speaker_label.isEnabled()
    assert not chat._character_menu.isVisible()
    pending_action.trigger()
    assert requested.count() == 0
    chat.set_waiting_for_reply(False)
    assert chat.current_speaker_label.isEnabled()
    assert [waiting.at(index) for index in range(waiting.count())] == [[True], [False]]


def test_character_without_sprite_clears_old_image_and_animation_state(chat, tmp_path):
    image = QImage(16, 32, QImage.Format.Format_ARGB32)
    image.fill(0xFF607B65)
    sprite = tmp_path / "sprite.png"
    image.save(str(sprite))
    chat.set_sprite(str(sprite))
    chat.set_sprite(str(sprite))
    chat.sprite_widget.play_click_bounce()
    chat.clear_sprite()
    assert chat.sprite_widget._source_pixmap is None
    assert chat.sprite_widget.pixmap().isNull()
    assert chat.sprite_widget._previous_fitted is None
    assert not chat.sprite_widget._frame_timer.isActive()
    assert chat.sprite_widget._hop_ms == chat.sprite_widget._click_scale_ms == 0
    assert not chat.sprite_widget.hit_test(chat.sprite_widget.rect().center())


def test_card_selection_saves_full_draft_and_persists_stable_id(settings):
    selected = QSignalSpy(settings.character_selected)
    buttons = settings.character_card_use_buttons
    assert [button.text() for button in buttons] == ["正在使用", "使用此角色"]
    assert not buttons[0].isEnabled()
    assert "下次启动" in buttons[1].toolTip()
    settings.char_setting_edit.setPlainText("A未保存的新设定")
    settings.char_name_edit.setText("A的新名字")
    buttons[1].click()
    assert selected.at(0) == ["character-b"]
    assert settings.config.system_config.active_character_id == "character-b"
    saved_characters = yaml.safe_load(ConfigManager._CHARACTERS_CONFIG_PATH.read_text(encoding="utf-8"))
    assert saved_characters[0]["memory_id"] == "character-a"
    assert saved_characters[0]["character_setting"] == "A未保存的新设定"
    assert saved_characters[0]["name"] == "A的新名字"
    assert yaml.safe_load(ConfigManager._SYSTEM_CONFIG_PATH.read_text(encoding="utf-8"))["active_character_id"] == "character-b"
    assert [button.text() for button in settings.character_card_use_buttons] == ["使用此角色", "正在使用"]


def test_embedded_card_saves_draft_before_request_without_changing_runtime_identity(settings):
    settings.set_character_switch_managed(True)
    assert "立即切换" in settings.character_card_use_buttons[1].toolTip()
    observations = []
    settings.character_selected.connect(lambda identity: observations.append((
        identity, settings.config.system_config.active_character_id,
        yaml.safe_load(ConfigManager._CHARACTERS_CONFIG_PATH.read_text(encoding="utf-8"))[0]["character_setting"],
    )))
    settings.char_setting_edit.setPlainText("保存后再发切换请求")
    settings._use_character("character-b")
    assert observations == [("character-b", "character-a", "保存后再发切换请求")]
    assert yaml.safe_load(ConfigManager._SYSTEM_CONFIG_PATH.read_text(encoding="utf-8"))["active_character_id"] == "character-a"
    settings.set_active_character_id("character-b")
    assert settings.config.system_config.active_character_id == "character-a"
    assert settings.character_card_use_buttons[1].text() == "正在使用"


def test_card_selection_preserves_other_character_and_system_drafts(settings):
    settings.char_setting_edit.setPlainText("A编辑中的草稿")
    settings.temp_spin.setValue(0.4)
    settings._open_character_detail(1)
    settings.char_setting_edit.setPlainText("B编辑中的草稿")
    settings._use_character("character-b")
    characters = yaml.safe_load(ConfigManager._CHARACTERS_CONFIG_PATH.read_text(encoding="utf-8"))
    assert [character["character_setting"] for character in characters] == ["A编辑中的草稿", "B编辑中的草稿"]
    assert settings.config.api_config.temperature == 0.4
    assert yaml.safe_load(ConfigManager._API_LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))["temperature"] == 0.4


def test_failed_save_does_not_switch_or_emit_and_keeps_editor_draft(settings, monkeypatch):
    selected = QSignalSpy(settings.character_selected)
    original_system = ConfigManager._SYSTEM_CONFIG_PATH.read_bytes()
    original_characters = ConfigManager._CHARACTERS_CONFIG_PATH.read_bytes()
    settings.char_setting_edit.setPlainText("保存失败也不能丢的草稿")
    monkeypatch.setattr(settings.config, "save_characters", lambda: (_ for _ in ()).throw(OSError("fixture write failed")))
    settings._use_character("character-b")
    assert selected.count() == 0
    assert settings.config.system_config.active_character_id == "character-a"
    assert settings._active_character_id == "character-a"
    assert settings.char_setting_edit.toPlainText() == "保存失败也不能丢的草稿"
    assert ConfigManager._SYSTEM_CONFIG_PATH.read_bytes() == original_system
    assert ConfigManager._CHARACTERS_CONFIG_PATH.read_bytes() == original_characters


def test_card_selection_ignores_unknown_id_and_generation_busy_state(settings):
    selected = QSignalSpy(settings.character_selected)
    settings._use_character("missing")
    settings.set_character_switch_enabled(False)
    assert all(not button.isEnabled() for button in settings.character_card_use_buttons)
    settings._use_character("character-b")
    assert selected.count() == 0
    settings.set_character_switch_enabled(True)
    assert settings.character_card_use_buttons[1].isEnabled()


def test_lazy_settings_preserves_startup_and_syncs_embedded_selection(settings):
    calls = []
    lazy = LazySettingsWindow(lambda: (calls.append("created"), settings)[1])
    selected = QSignalSpy(lazy.character_selected)
    lazy.set_active_character_id("character-a")
    lazy.set_character_switch_enabled(False)
    assert not lazy.is_created and calls == []
    lazy.show()
    assert calls == ["created"]
    assert settings._character_switch_managed
    assert not settings.character_card_use_buttons[1].isEnabled()
    lazy.set_character_switch_enabled(True)
    settings._use_character("character-b")
    assert selected.at(0) == ["character-b"]
    assert settings.config.system_config.active_character_id == "character-a"
    lazy.set_active_character_id("character-b")
    assert settings.character_card_use_buttons[1].text() == "正在使用"
