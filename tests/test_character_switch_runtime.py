"""Real Qt + on-disk fixtures for persona/history switching; no model calls."""
from queue import Queue
from types import SimpleNamespace as NS

import pytest
from PySide6.QtCore import QObject, Signal, QCoreApplication, QEvent
from PySide6.QtTest import QTest
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication

from config.config_manager import ConfigManager
from config.schema import AppConfig, Character, SystemConfig
from core.runtime.app_runtime import clear_app_runtime
from core.runtime.character_switch import CharacterSwitchController
from core.runtime.chat_app import create_initial_chat_display
from core.runtime.llm_setup import LLMRuntimeContext, build_active_character_template, create_llm_runtime_context
from core.runtime.llm_ui_handlers import LLMUiHandlers
from core.runtime.runtime_setup import create_runtime_setup
from core.runtime.turn_controller import TurnController
from core.runtime.ui_worker_handlers import UIWorkerHandlers
from core.runtime.cancellation import TurnEvent
from core.runtime.chat_actions import handle_new_session_requested, handle_archive_session_requested, handle_delete_session_requested
from core.sessions.store import SessionStore
from core.sprite import chat_history as history
from llm.llm_manager import LLMManager
from llm.tools.tool_manager import ToolManager
from ui.chat_ui.chat_ui import ChatUIWindow


class Worker(QObject):
    turn_event = Signal(object)


class Audio:
    def __init__(self):
        self.played = []
        self.stopped = 0

    def play(self, path):
        self.played.append(path)

    def stop(self):
        self.stopped += 1


@pytest.fixture
def switched(tmp_path, monkeypatch):
    # Redirect EVERY ConfigManager file and the shared history journal first.
    for name in ("API_CONFIG", "API_LOCAL_CONFIG", "CHARACTERS_CONFIG", "SYSTEM_CONFIG", "BACKGROUND_CONFIG", "MCP_CONFIG"):
        monkeypatch.setattr(ConfigManager, "_" + name + "_PATH", tmp_path / "config" / (name.lower() + ".yaml"))
    monkeypatch.setattr(ConfigManager, "_instance", None)
    monkeypatch.setattr(ConfigManager, "_config", None)
    import socket
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **kw: pytest.fail("A character switch must not call a service"))
    config = ConfigManager()
    characters = []
    for identity, name, color, scale in (("A", "小芽", "#718772", 0.8), ("B", "小雪", "#678ABC", 1.3)):
        image = QImage(32, 64, QImage.Format.Format_ARGB32)
        image.fill(QColor(color))
        image_path = tmp_path / (identity + ".png")
        assert image.save(str(image_path))
        characters.append(Character(memory_id=identity, name=name, color=color,
                                    character_setting=identity + "_PRIVATE_PERSONA",
                                    sprite_scale=scale, sprites=[{"id": 0, "path": str(image_path)}]))
    config._config = AppConfig(characters=characters, system_config=SystemConfig(skills_root=str(tmp_path / "skills")))
    app = QApplication.instance() or QApplication([])
    old_store, old_id, old_ui_history = history.get_session_store(), history.get_active_session_id(), list(history.get_history())
    store = SessionStore(history_root=tmp_path / "history", sessions_dir=tmp_path / "history" / "sessions",
                         index_path=tmp_path / "history" / "sessions.json", legacy_default_file=tmp_path / "history" / "default.json")
    history.set_session_store(store)
    history.get_history().clear()
    manager = LLMManager(adapter=object(), user_template=build_active_character_template(config))
    context = LLMRuntimeContext(manager, characters[0].name, characters[0].color)
    setup = create_runtime_setup(config, manager, None)
    setup.runtime.tool_manager = ToolManager()
    session_a = history.ensure_default_session()
    assert history.load_session(session_a.id)
    window = ChatUIWindow()
    sprites = create_initial_chat_display(window, config, context, history)
    audio = Audio()
    llm_handlers = LLMUiHandlers(window, history, context.active_character_name, context.active_character_color, sprites.set_sprite_by_id)
    ui_handlers = UIWorkerHandlers(window, config, audio.play)
    workers = NS(llm_worker=Worker(), ui_worker=Worker(), t2i_worker=None)
    turns = TurnController(window, workers, setup, history, llm_handlers, ui_handlers, audio)
    controller = CharacterSwitchController(window, config, history, context, sprites, llm_handlers, turns)
    fixture = NS(config=config, window=window, sprites=sprites, context=context, controller=controller, history=history,
                 store=store, session_a=session_a, turns=turns, setup=setup, llm_handlers=llm_handlers,
                 audio=audio, app=app, tmp=tmp_path)
    try:
        yield fixture
    finally:
        turns.memory_service.close()
        window.prepare_runtime_close = lambda: True
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        clear_app_runtime()
        history.set_session_store(old_store)
        history._active_session_id = old_id
        history.get_history()[:] = old_ui_history


def record(fixture, text):
    fixture.context.manager.add_user_message(text)
    fixture.history.add_to_history("user", text)
    fixture.history.save()


def test_a_b_a_restores_independent_persona_history_artwork_and_drafts(switched):
    s = switched
    record(s, "A_ONLY_CHAT")
    s.window.input_edit.setText("A draft")
    s.window.character_requested.emit("B")
    session_b = s.history.get_active_session_id()
    assert session_b != s.session_a.id
    assert "B_PRIVATE_PERSONA" in s.context.manager.user_template
    assert "A_PRIVATE_PERSONA" not in s.context.manager.user_template
    assert s.history.get_history() == []
    assert "A_ONLY_CHAT" not in str(s.context.manager.get_messages())
    assert s.sprites.character_index == 1 and s.sprites._scale() == 1.3
    assert s.llm_handlers.active_character_name == "小雪"
    assert s.window.input_edit.text() == ""
    record(s, "B_ONLY_CHAT")
    s.window.input_edit.setText("B draft")
    assert s.controller.select("A")
    assert s.history.get_active_session_id() == s.session_a.id
    assert s.history.get_history() == [{"role": "user", "content": "A_ONLY_CHAT"}]
    assert "B_ONLY_CHAT" not in str(s.context.manager.get_messages())
    assert "A_PRIVATE_PERSONA" in s.context.manager.user_template
    assert s.window.input_edit.text() == "A draft"
    assert s.sprites._scale() == 0.8
    assert s.controller.select("B")
    assert s.history.get_active_session_id() == session_b
    assert s.window.input_edit.text() == "B draft"
    assert {session.character_id for session in s.history.list_sessions(include_archived=True)} == {"B"}


def test_selected_identity_and_history_survive_restart_and_reordering(switched, monkeypatch):
    s = switched
    record(s, "A must stay with A")
    assert s.controller.select("B")
    record(s, "B survives restart")
    session_b = s.history.get_active_session_id()
    ConfigManager.reset()
    reloaded = ConfigManager()
    assert reloaded.system_config.active_character_id == "B"
    reloaded.characters.reverse()
    s.setup.runtime.config = reloaded
    monkeypatch.setattr("core.runtime.llm_setup.LLMAdapterFactory.create_adapter", lambda **kwargs: object())
    context = create_llm_runtime_context(reloaded)
    assert context.active_character_name == "小雪"
    s.setup.runtime.llm_manager = context.manager
    restored = s.history.ensure_default_session()
    assert restored.id == session_b
    assert s.history.load_session(restored.id)
    assert "B survives restart" in str(context.manager.get_messages())
    assert "A must stay with A" not in str(context.manager.get_messages())


@pytest.mark.parametrize("kind", ["dialog_parsed", "status_changed", "tool_summary_ready", "stream_end", "ui_options", "ui_dialog", "image_generated", "generation_failed"])
def test_late_events_from_previous_character_are_ignored(switched, kind):
    s = switched
    s.history.add_to_history("user", "A in flight")
    s.turns.enqueue("A in flight")
    old_token = s.turns.token
    assert s.controller.select("B")
    messages, ui = s.context.manager.get_messages(), list(s.history.get_history())
    # Invalid payload deliberately fails loudly if a stale handler is invoked.
    s.turns.receive(TurnEvent(old_token, kind, object()))
    assert old_token.cancelled.is_set()
    assert s.context.manager.get_messages() == messages
    assert s.history.get_history() == ui == []
    assert not s.audio.played
    assert s.audio.stopped >= 1
    assert "A in flight" in s.store.read_session_payload(s.session_a.id)["messages"][-2]["content"]


def test_persistence_failure_rolls_back_persona_session_and_draft(switched, monkeypatch):
    s = switched
    record(s, "keep A")
    s.window.input_edit.setText("do not lose this")
    old_messages = s.context.manager.get_messages()
    monkeypatch.setattr(s.config, "save_system_config", lambda: (_ for _ in ()).throw(OSError("fixture write error")))
    assert not s.controller.select("B")
    assert s.config.system_config.active_character_id == ""
    assert s.history.get_active_session_id() == s.session_a.id
    assert s.context.manager.get_messages() == old_messages
    assert s.window.input_edit.text() == "do not lose this"
    assert s.window.input_edit.isEnabled()


def test_switch_does_not_scan_or_copy_the_entire_user_asset_library(switched, monkeypatch):
    from pathlib import Path
    s = switched
    asset = s.tmp / "sprites" / "unrelated-large-library.png"
    asset.parent.mkdir()
    asset.write_bytes(b"private fixture asset")
    read_bytes = Path.read_bytes

    def checked_read(path):
        if path == asset:
            pytest.fail("Selecting a role must not read unrelated sprite library files")
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", checked_read)
    assert s.controller.select("B")


def test_corrupt_target_is_retained_and_cannot_receive_outgoing_chat(switched):
    s = switched
    record(s, "preserve A")
    assert s.controller.select("B")
    target = s.history.get_active_session_id()
    assert s.controller.select("A")
    path = s.store.session_history_path(target)
    path.write_text("{broken JSON", encoding="utf-8")
    assert not s.controller.select("B")
    assert path.read_text(encoding="utf-8") == "{broken JSON"
    assert s.history.get_active_session_id() == s.session_a.id
    assert "B_PRIVATE_PERSONA" not in s.context.manager.user_template
    assert "preserve A" in str(s.context.manager.get_messages())


def test_session_actions_only_show_and_select_sessions_for_active_role(switched):
    s = switched
    record(s, "A archive remains")
    assert s.controller.select("B")
    session_b = s.history.get_active_session_id()
    handle_new_session_requested(s.window, s.history, s.llm_handlers.char_color, character_name="小雪", config=s.config)
    newer_b = s.history.get_active_session_id()
    assert newer_b != session_b
    handle_delete_session_requested(s.window, s.history, s.llm_handlers.char_color, newer_b)
    assert s.history.get_active_session_id() == session_b
    handle_archive_session_requested(s.window, s.history, s.llm_handlers.char_color, session_b, True)
    assert s.history.get_active_session_id() not in {session_b, s.session_a.id}
    assert {item["id"] for item in s.window._session_items}.isdisjoint({s.session_a.id})
    assert not s.history.switch_session(s.session_a.id)
    assert s.config.current_character.memory_id == "B"


def test_settings_use_button_switches_the_real_shared_runtime_after_saving_drafts(switched, monkeypatch):
    from core.runtime.lazy_settings import LazySettingsWindow
    from core.security.allowed_roots import AllowedRootsStore
    from ui.settings_ui.window import SettingsWindow
    from PySide6.QtWidgets import QMessageBox
    s = switched
    record(s, "A separate log")
    monkeypatch.chdir(s.tmp)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **kw: pytest.fail("Settings should save"))

    def factory():
        settings = SettingsWindow(allowed_roots_store=AllowedRootsStore(s.tmp / "roots.json", project_root=s.tmp))
        monkeypatch.setattr(settings, "_build_template_preflight_report", lambda **kwargs: ("ok", "通过"))
        return settings

    lazy = LazySettingsWindow(factory)
    s.controller.settings = lazy
    lazy.character_selected.connect(s.controller.select)
    s.controller._sync_selection()
    lazy.show()
    settings = lazy._window
    try:
        settings._open_character_detail(1)
        settings.char_setting_edit.setPlainText("B_EDITED_PERSONA")
        # This is the exact card action, through LazySettingsWindow's signal.
        settings._use_character("B")
        assert s.controller.active_id == "B"
        assert settings._active_character_id == "B"
        assert "B_EDITED_PERSONA" in s.context.manager.user_template
        assert "A_PRIVATE_PERSONA" not in s.context.manager.user_template
        assert not s.history.get_history()
        assert s.sprites.character_index == 1
        previous = s.store.read_session_payload(s.session_a.id)
        assert previous["character_id"] == "A"
        assert "A separate log" in str(previous["messages"])
        assert "A separate log" not in str(s.context.manager.get_messages())
        assert s.config.characters[1].character_setting == "B_EDITED_PERSONA"
        assert settings.character_card_use_buttons[1].text() == "正在使用"
        # Newly saved roster entries also appear from the home menu immediately.
        s.config.characters.append(Character(memory_id="C", name="新伙伴"))
        s.window._show_character_menu()
        assert [action.data() for action in s.window._character_menu.actions()] == ["A", "B", "C"]
    finally:
        settings._settings_dirty = False
        lazy.close()
        settings.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        s.app.processEvents()


def test_real_llm_thread_cancellation_keeps_the_next_character_clean(switched):
    import threading
    import time
    from PySide6.QtCore import Qt
    from core.runtime.llm_worker import LLMWorker
    s = switched
    entered, release = threading.Event(), threading.Event()

    class BlockedAdapter:
        calls = 0

        def generate(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                entered.set()
                assert release.wait(3)
                return {"content": '{"name":"小芽","speech":"A_LATE_REPLY","asset_id":"0"}', "tool_calls": []}
            assert "B_PRIVATE_PERSONA" in str(messages)
            assert "A_PRIVATE_PERSONA" not in str(messages)
            assert "A_LATE_REPLY" not in str(messages)
            assert "A_IN_FLIGHT" not in str(messages)
            return {"content": '{"name":"小雪","speech":"B_REAL_REPLY","asset_id":"0"}', "tool_calls": []}

    s.context.manager.adapter = BlockedAdapter()
    worker = LLMWorker(s.setup.user_input_queue, s.setup.tts_queue)
    worker.turn_event.connect(s.turns.receive, Qt.ConnectionType.QueuedConnection)
    worker.start()
    try:
        s.history.add_to_history("user", "A_IN_FLIGHT")
        s.turns.enqueue("A_IN_FLIGHT")
        assert entered.wait(3)
        assert s.controller.select("B")
        release.set()
        s.history.add_to_history("user", "B_INPUT")
        s.turns.enqueue("B_INPUT")
        deadline = time.monotonic() + 4
        while (s.turns.pending or s.window._waiting_for_reply) and time.monotonic() < deadline:
            QTest.qWait(10)
        assert not s.turns.pending
        assert not s.window._waiting_for_reply
        assert "B_REAL_REPLY" in str(s.history.get_history())
        assert "A_LATE_REPLY" not in str(s.history.get_history())
        assert "A_IN_FLIGHT" not in str(s.context.manager.get_messages())
        assert s.store.get_session(s.history.get_active_session_id()).character_id == "B"
    finally:
        release.set()
        worker.stop()
        assert worker.wait(3000)
