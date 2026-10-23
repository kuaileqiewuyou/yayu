"""Exercise settings persistence and live motion changes using real Qt widgets."""
import os
import json

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import yaml
from PySide6.QtCore import QEvent
from PySide6.QtGui import QFontDatabase, QFontInfo, QImage, QRawFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from config.config_manager import ConfigManager
from config.schema import SystemConfig
from core.security.allowed_roots import AllowedRootsStore
from ui import motion
from ui.chat_ui.chat_ui import ChatUIWindow
from ui.resources import FONT_FAMILY, chrome_icon, ensure_ui_font
from ui.settings_ui.window import SettingsWindow


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def restore_motion():
    motion.apply_system_config(SystemConfig())
    yield
    motion.apply_system_config(SystemConfig())


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in ("API_CONFIG", "API_LOCAL_CONFIG", "SYSTEM_CONFIG", "CHARACTERS_CONFIG", "BACKGROUND_CONFIG", "MCP_CONFIG"):
        monkeypatch.setattr(ConfigManager, f"_{name}_PATH", tmp_path / f"{name.lower()}.yaml")
    ConfigManager.reset()
    ConfigManager._CHARACTERS_CONFIG_PATH.write_text(
        yaml.safe_dump([{"name": "测试角色", "character_setting": "友善的对话伙伴", "emotion_tags": "0: neutral"}], allow_unicode=True),
        encoding="utf-8",
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **kw: None)
    w = SettingsWindow(allowed_roots_store=AllowedRootsStore(tmp_path / "roots.json", project_root=tmp_path))
    w.template_sample_output_edit.setPlainText(json.dumps({"character_name": "测试角色", "speech": "你好", "sprite": "0"}, ensure_ascii=False))
    w._settings_dirty = False
    yield w
    w._settings_dirty = False
    w.close()
    ConfigManager.reset()


def test_motion_controls_load_and_save_then_reload_from_disk(window):
    assert not window.reduce_motion_check.isChecked()
    assert window.typewriter_enabled_check.isChecked()
    assert window.typewriter_cps_spin.value() == 40
    window.typewriter_cps_spin.setValue(73)
    window.reduce_motion_check.setChecked(True)
    assert not window.typewriter_enabled_check.isEnabled()
    assert not window.typewriter_cps_spin.isEnabled()

    window._save_config()

    stored = yaml.safe_load(ConfigManager._SYSTEM_CONFIG_PATH.read_text(encoding="utf-8"))
    assert stored["reduce_motion"] is True
    assert stored["typewriter_enabled"] is True
    assert stored["typewriter_cps"] == 73
    assert motion.reduced_motion()
    ConfigManager.reset()
    cfg = ConfigManager().system_config
    assert (cfg.reduce_motion, cfg.typewriter_enabled, cfg.typewriter_cps) == (True, True, 73)
    window.config = ConfigManager()
    window._load_config()
    window.reduce_motion_check.setChecked(False)
    assert window.typewriter_enabled_check.isEnabled()
    assert window.typewriter_cps_spin.isEnabled()
    assert window.typewriter_cps_spin.value() == 73


def test_disabling_typewriter_keeps_speed_and_marks_settings_dirty(window):
    window.typewriter_cps_spin.setValue(85)
    window.typewriter_enabled_check.setChecked(False)
    assert window._settings_dirty
    assert not window.typewriter_cps_spin.isEnabled()
    window.typewriter_enabled_check.setChecked(True)
    assert window.typewriter_cps_spin.value() == 85


def test_failed_save_preserves_input_and_live_preferences(window, monkeypatch):
    def fail():
        raise OSError("simulated write failure")
    monkeypatch.setattr(window.config, "save_system_config", fail)
    window.reduce_motion_check.setChecked(True)
    window.typewriter_cps_spin.setValue(91)
    window._save_config()
    assert not motion.reduced_motion()
    assert window._settings_dirty
    assert window.reduce_motion_check.isChecked()
    assert window.typewriter_cps_spin.value() == 91
    assert "失败" in window.save_status_label.text()


def test_page_transition_finishes_on_rapid_switch_resize_and_reduce_motion(window, app):
    window.show()
    app.processEvents()
    window.settings_nav.setCurrentRow(4)
    assert window.settings_tabs.currentIndex() == 4
    assert window._page_transition._timer.isActive()
    window.settings_nav.setCurrentRow(0)
    window.settings_nav.setCurrentRow(4)
    QTest.qWait(motion.PAGE + 50)
    assert not window._page_transition.isVisible()
    assert not window._page_transition._timer.isActive()
    window.settings_nav.setCurrentRow(0)
    window.resize(window.width() + 20, window.height())
    app.processEvents()
    assert not window._page_transition.isVisible()
    window.reduce_motion_check.setChecked(True)
    window.settings_nav.setCurrentRow(4)
    assert not window._page_transition._timer.isActive()


def test_live_reduced_motion_stops_thinking_idle_and_current_reveal(app, tmp_path):
    sprite_path = tmp_path / "sprite.png"
    image = QImage(20, 40, QImage.Format.Format_RGB32)
    image.fill(0x607B65)
    image.save(str(sprite_path))
    chat = ChatUIWindow()
    try:
        chat.set_sprite(str(sprite_path))
        chat.show()
        app.processEvents()
        chat.add_message("这段台词正在逐字显示。", char_name="角色")
        assert chat.current_message_label.is_revealing()
        assert chat.sprite_widget.is_animating()
        motion.apply_system_config(SystemConfig(reduce_motion=True))
        assert not chat.current_message_label.is_revealing()
        assert not chat.current_message_label._frame_timer.isActive()
        assert not chat.sprite_widget.is_animating()
        chat.add_message("在吗？", is_user=True)
        chat.set_waiting_for_reply(True)
        assert chat.current_message_label.is_thinking()
        assert not chat.current_message_label._frame_timer.isActive()
        chat._set_ui_visible(False)
        assert chat._overlay_anim is None
        assert not chat.overlay_layer.isVisible()
        chat._set_ui_visible(True)
        assert chat.overlay_layer.isVisible()
    finally:
        chat.close()


def test_svg_icons_rasterize_and_bundled_font_has_simplified_chinese(app):
    ensure_ui_font()
    assert FONT_FAMILY in QFontDatabase.families()
    assert QFontInfo(app.font()).family() == FONT_FAMILY
    raw = QRawFont.fromFont(app.font())
    assert all(raw.supportsCharacter(ord(c)) for c in "设置动效角色台词减少速度欢迎回来保存配置ABC012")
    for name in ("history", "settings", "close", "minus", "info", "eye", "eye-off", "more", "maximize", "restore"):
        pixels = chrome_icon(name).pixmap(24, 24).toImage()
        assert not pixels.isNull()
        assert any(pixels.pixelColor(x, y).alpha() for x in range(24) for y in range(24))


def test_chat_event_filter_tolerates_popup_attribute_cleanup(app):
    chat = ChatUIWindow()
    popup = chat.conversation_info_popup
    del chat.conversation_info_popup
    try:
        assert chat.eventFilter(QWidget(), QEvent(QEvent.Type.Hide)) is False
    finally:
        chat.conversation_info_popup = popup
        chat.close()
