"""Actual settings-save signals through lazy windows to the chat window flags."""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import yaml
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QMessageBox

from config.config_manager import ConfigManager
from core.runtime import chat_app
from core.security.allowed_roots import AllowedRootsStore
from ui.settings_ui.window import SettingsWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def context(app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in ("API_CONFIG", "API_LOCAL_CONFIG", "SYSTEM_CONFIG", "CHARACTERS_CONFIG", "BACKGROUND_CONFIG", "MCP_CONFIG"):
        monkeypatch.setattr(ConfigManager, f"_{name}_PATH", tmp_path / f"{name.lower()}.yaml")
    ConfigManager._SYSTEM_CONFIG_PATH.write_text("{}", encoding="utf-8")
    ConfigManager._CHARACTERS_CONFIG_PATH.write_text(yaml.safe_dump([
        {"name": "测试角色", "character_setting": "友善的对话伙伴", "emotion_tags": "0: neutral"},
    ], allow_unicode=True), encoding="utf-8")
    ConfigManager.reset()
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **kw: None)

    def make_settings():
        w = SettingsWindow(allowed_roots_store=AllowedRootsStore(tmp_path / "roots.json", project_root=tmp_path))
        w.template_sample_output_edit.setPlainText(json.dumps({
            "character_name": "测试角色", "speech": "你好", "sprite": "0",
        }, ensure_ascii=False))
        w._settings_dirty = False
        return w

    monkeypatch.setattr(chat_app, "create_settings_window", make_settings)
    chat, lazy = chat_app.create_chat_windows(ConfigManager())
    yield chat, lazy
    if lazy.is_created:
        lazy._window._settings_dirty = False
        lazy._window.close()
        lazy._window.deleteLater()
    chat.close()
    chat.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    ConfigManager.reset()


def is_on_top(chat):
    return bool(chat.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)


def test_old_configuration_defaults_off_and_startup_keeps_settings_lazy(context):
    chat, lazy = context
    assert not ConfigManager().system_config.always_on_top
    assert not is_on_top(chat)
    assert not chat.isVisible()
    assert not lazy.is_created
    lazy.show()
    assert not lazy._window.always_on_top_check.isChecked()
    assert not lazy._window._settings_dirty


def test_save_applies_immediately_preserves_chat_and_remembers_disable(context, app):
    chat, lazy = context
    chat.resize(700, 600)
    chat.move(50, 50)
    chat.show()
    app.processEvents()
    rectangle = chat.geometry()
    chat.input_edit.setText("尚未发送的内容")
    lazy.show()
    window = lazy._window
    assert window.windowHandle().transientParent() is chat.windowHandle()
    window.always_on_top_check.setChecked(True)
    assert window._settings_dirty
    assert not is_on_top(chat)
    window._save_config()
    assert is_on_top(chat)
    assert is_on_top(window)
    assert chat.isVisible()
    assert window.isVisible()
    assert window.windowHandle().transientParent() is chat.windowHandle()
    assert chat.geometry() == rectangle
    assert chat.input_edit.text() == "尚未发送的内容"
    assert chat.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert chat.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert not window._settings_dirty
    stored = yaml.safe_load(ConfigManager._SYSTEM_CONFIG_PATH.read_text(encoding="utf-8"))
    assert stored["always_on_top"] is True
    window.always_on_top_check.setChecked(False)
    window._save_config()
    assert not is_on_top(chat)
    assert not is_on_top(window)
    assert window.isVisible()
    assert window.windowHandle().transientParent() is chat.windowHandle()
    assert chat.geometry() == rectangle
    assert chat.input_edit.text() == "尚未发送的内容"
    assert yaml.safe_load(ConfigManager._SYSTEM_CONFIG_PATH.read_text(encoding="utf-8"))["always_on_top"] is False


def test_saved_preference_is_applied_at_next_startup_without_opening_settings(context):
    chat, lazy = context
    lazy.show()
    lazy._window.always_on_top_check.setChecked(True)
    lazy._window._save_config()
    ConfigManager.reset()
    next_chat, next_lazy = chat_app.create_chat_windows(ConfigManager())
    try:
        assert is_on_top(next_chat)
        assert not next_chat.isVisible()
        assert not next_lazy.is_created
        next_lazy.show()
        assert is_on_top(next_lazy._window)
    finally:
        if next_lazy.is_created:
            next_lazy._window._settings_dirty = False
            next_lazy._window.close()
            next_lazy._window.deleteLater()
        next_chat.close()
        next_chat.deleteLater()


def test_failed_save_keeps_draft_but_does_not_change_live_window(context, monkeypatch):
    chat, lazy = context
    lazy.show()
    window = lazy._window
    before = ConfigManager._SYSTEM_CONFIG_PATH.read_bytes()
    signal = QSignalSpy(lazy.always_on_top_changed)

    def fail():
        raise OSError("simulated write failure")

    monkeypatch.setattr(window.config, "save_system_config", fail)
    window.always_on_top_check.setChecked(True)
    window._save_config()
    assert not is_on_top(chat)
    assert not window.config.system_config.always_on_top
    assert window.always_on_top_check.isChecked()
    assert window._settings_dirty
    assert signal.count() == 0
    assert "失败" in window.save_status_label.text()
    assert ConfigManager._SYSTEM_CONFIG_PATH.read_bytes() == before


@pytest.mark.parametrize("state", ["hidden", "minimized", "maximized"])
def test_changing_preference_preserves_window_visibility_and_state(context, app, state):
    chat, lazy = context
    chat.resize(700, 600)
    if state == "minimized":
        chat.showMinimized()
    elif state == "maximized":
        chat.showMaximized()
    app.processEvents()
    visible = chat.isVisible()
    window_state = chat.windowState()
    for enabled in (True, False):
        chat.set_always_on_top(enabled)
        app.processEvents()
        assert is_on_top(chat) == enabled
        assert chat.isVisible() == visible
        assert chat.windowState() == window_state
