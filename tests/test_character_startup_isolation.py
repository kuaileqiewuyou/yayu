"""Startup must select the role before restoring its prompt and transcript."""
import json
from types import SimpleNamespace as NS

import pytest

from config.config_manager import ConfigManager
from config.schema import AppConfig, Character, SystemConfig
from core.runtime import chat_app
from core.runtime.app_runtime import clear_app_runtime
from core.runtime.llm_setup import LLMRuntimeContext
from core.runtime.runtime_setup import create_runtime_setup
from core.sessions.store import SessionStore
from core.sprite import chat_history as history
from llm.llm_manager import LLMManager


@pytest.fixture
def startup(tmp_path, monkeypatch):
    for field in ("API", "API_LOCAL", "CHARACTERS", "SYSTEM", "BACKGROUND", "MCP"):
        monkeypatch.setattr(ConfigManager, f"_{field}_CONFIG_PATH", tmp_path / "config" / (field + ".yaml"))
    monkeypatch.setattr(ConfigManager, "_instance", None)
    monkeypatch.setattr(ConfigManager, "_config", None)
    import socket
    monkeypatch.setattr(socket.socket, "connect", lambda *args, **kwargs: pytest.fail("Startup must not call a model"))
    config = ConfigManager()
    characters = [Character(memory_id=identity, name=identity, character_setting=identity + "_PERSONA",
                            default_skills=[identity + "-default"], sprite_scale=scale,
                            sprites=[{"id": 0, "path": str(tmp_path / (identity + ".png"))}])
                  for identity, scale in (("A", .8), ("B", 1.2))]
    config._config = AppConfig(characters=characters,
                              system_config=SystemConfig(active_character_id="B", skills_root=str(tmp_path / "skills"),
                                                         default_skills=["global-default"]))
    for name in ("A-only", "B-only", "global-default", "A-default", "B-default"):
        path = tmp_path / "skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(f"---\nname: {name}\ndescription: fixture\n---\n{name.upper()}_INSTRUCTIONS\n", encoding="utf-8")
    store = SessionStore(history_root=tmp_path / "history", sessions_dir=tmp_path / "history" / "sessions",
                         index_path=tmp_path / "history" / "sessions.json", legacy_default_file=tmp_path / "history" / "default.json")
    monkeypatch.setattr(history, "_session_store", store)
    monkeypatch.setattr(history, "_active_session_id", None)
    monkeypatch.setattr(history, "chat_history", [])
    sessions = {}
    for identity in ("A", "B"):
        session = store.create_session(title=identity, character_name=identity, character_id=identity, make_active=False)
        store.update_enabled_skills(session.id, [identity + "-only"])
        store.write_session_payload(session.id, {"character_id": identity,
            "messages": [{"role": "system", "content": identity + "_OLD_PERSONA"},
                         {"role": "user", "content": identity + "_PRIVATE_CHAT"}],
            "ui_history": [{"role": "user", "content": identity + "_PRIVATE_CHAT"}]})
        sessions[identity] = session
    store.set_active_session(sessions["A"].id)
    history._active_session_id = sessions["A"].id
    manager = LLMManager(adapter=object(), user_template="STALE_A_PROMPT")
    setup = create_runtime_setup(config, manager, None)
    worker_calls = []
    monkeypatch.setattr(chat_app, "create_runtime_workers", lambda *args, **kwargs: worker_calls.append("created") or NS())
    yield NS(config=config, store=store, sessions=sessions, manager=manager, setup=setup, workers=worker_calls)
    clear_app_runtime()


def test_native_startup_selected_b_uses_b_prompt_skills_history_and_sprite(startup):
    s = startup
    chat_app.create_runtime_workers_after_history_load(s.setup, None, history, character_name="B")
    assert history.get_active_session_id() == s.sessions["B"].id
    assert "B_PERSONA" in s.manager.user_template
    assert "B-ONLY_INSTRUCTIONS" in s.manager.user_template
    assert "A-ONLY_INSTRUCTIONS" not in s.manager.user_template
    assert "B_PRIVATE_CHAT" in str(s.manager.get_messages())
    assert "A_PRIVATE_CHAT" not in str(s.manager.get_messages())
    assert "B_OLD_PERSONA" not in str(s.manager.get_messages())
    sprites = []
    window = NS(set_active_character_name=lambda name: None, add_message=lambda *args, **kwargs: None,
                set_sprite=lambda path, scale: sprites.append((path, scale)))
    controller = chat_app.create_initial_chat_display(window, s.config, LLMRuntimeContext(s.manager, "B", "#FFFFFF"), history)
    assert controller.character_index == 1
    assert sprites == [(s.config.characters[1].sprites[0].path, 1.2)]
    assert s.workers == ["created"]
    assert s.setup.history_recovery_notice == ""


@pytest.mark.parametrize("bad_payload", ["{broken", '["bad entry"]', '{"messages": [4]}',
                                       '{"messages": [], "ui_history": [null]}'])
def test_corrupt_selected_b_is_preserved_and_new_b_session_is_used(startup, bad_payload):
    s = startup
    path = s.store.session_history_path(s.sessions["B"].id)
    path.write_text(bad_payload, encoding="utf-8")
    before = path.read_bytes()
    chat_app.create_runtime_workers_after_history_load(s.setup, None, history, character_name="B")
    active = s.store.get_session(history.get_active_session_id())
    assert active.id not in {session.id for session in s.sessions.values()}
    assert active.character_id == "B"
    assert active.enabled_skills == ["global-default", "B-default"]
    assert history.get_history() == []
    assert [message["role"] for message in s.manager.get_messages()] == ["system"]
    assert "B_PERSONA" in s.manager.user_template and "A_PERSONA" not in s.manager.user_template
    assert "B-DEFAULT_INSTRUCTIONS" in s.manager.user_template
    assert "A-ONLY_INSTRUCTIONS" not in s.manager.user_template
    assert "原文件已保留" in s.setup.history_recovery_notice
    history.save()
    assert path.read_bytes() == before
    assert s.workers == ["created"]


def test_failed_safe_replacement_stops_startup_before_workers(startup, monkeypatch):
    s = startup
    path = s.store.session_history_path(s.sessions["B"].id)
    path.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(history, "load_session", lambda session_id: False)
    with pytest.raises(RuntimeError, match="停止启动"):
        chat_app.create_runtime_workers_after_history_load(s.setup, None, history)
    assert s.workers == []
    assert path.read_text(encoding="utf-8") == "{broken"


def test_invalid_utf8_selected_transcript_is_preserved_during_recovery(startup):
    s = startup
    path = s.store.session_history_path(s.sessions["B"].id)
    path.write_bytes(b"\xff\xfe\x00")
    chat_app.create_runtime_workers_after_history_load(s.setup, None, history)
    history.save()
    assert path.read_bytes() == b"\xff\xfe\x00"
    assert s.store.get_session(history.get_active_session_id()).character_id == "B"


def test_new_default_initializes_defaults_but_existing_empty_skill_selection_stays_empty(startup):
    s = startup
    store = s.store
    store.update_enabled_skills(s.sessions["B"].id, [])
    assert history.ensure_character_session().enabled_skills == []
    store.archive_session(s.sessions["B"].id)
    created = history.ensure_character_session()
    assert created.id != s.sessions["B"].id
    assert created.enabled_skills == ["global-default", "B-default"]
    store.update_enabled_skills(created.id, [])
    assert history.ensure_character_session().enabled_skills == []


def test_recovery_notice_is_shown_after_chat_window_is_built(startup, monkeypatch):
    s = startup
    s.store.session_history_path(s.sessions["B"].id).write_text("{broken", encoding="utf-8")
    calls = []
    window = NS(set_reply_status=lambda text, **kwargs: calls.append((text, kwargs)))
    settings = NS(set_mcp_runtime_controller=lambda controller: None, refresh_mcp_status=lambda status: None)
    monkeypatch.setattr(chat_app, "QApplication", lambda argv: NS(setStyleSheet=lambda stylesheet: None))
    monkeypatch.setattr(chat_app, "prepare_application_identity", lambda identity: None)
    monkeypatch.setattr(chat_app, "apply_application_icon", lambda app: None)
    monkeypatch.setattr(chat_app, "init_i18n", lambda language: None)
    monkeypatch.setattr(chat_app, "apply_motion_preferences", lambda system: None)
    context = LLMRuntimeContext(s.manager, "B", "#FFFFFF")
    monkeypatch.setattr(chat_app, "create_core_runtime_components", lambda config: NS(
        llm_context=context, tts_manager=None, t2i_manager=None, runtime_setup=s.setup, mcp_controller=object(), mcp_status=None))
    monkeypatch.setattr(chat_app, "create_chat_windows", lambda config: (window, settings))
    monkeypatch.setattr(chat_app, "apply_mcp_status_startup_notice", lambda *args: None)
    monkeypatch.setattr(chat_app, "create_initial_chat_display", lambda *args: object())
    monkeypatch.setattr(chat_app, "AudioPlayer", lambda: object())
    monkeypatch.setattr(chat_app, "wire_runtime_signals", lambda **kwargs: object())
    handles = chat_app.build_chat_app([])
    assert handles.window is window
    assert calls == [(s.setup.history_recovery_notice, {"error": True})]


@pytest.mark.parametrize("payload", ["{broken", '["bad entry"]', '{"messages": [4]}',
                                  '{"character_id": "B", "messages": [], "ui_history": []}'])
def test_continuing_corrupt_or_wrong_bound_source_keeps_original_pointer_and_files(startup, payload):
    s = startup
    s.config.system_config.active_character_id = "A"
    own = s.sessions["A"]
    assert history.load_session(own.id)
    path = s.store.session_history_path(own.id)
    path.write_text(payload, encoding="utf-8")
    before = s.store.load_index().to_dict()
    messages = s.manager.get_messages()
    assert history.continue_session(own.id) is None
    assert s.store.load_index().to_dict() == before
    assert history.get_active_session_id() == own.id
    assert s.manager.get_messages() == messages
    assert path.read_text(encoding="utf-8") == payload


def test_continuation_load_failure_discards_only_new_copy(startup, monkeypatch):
    s = startup
    s.config.system_config.active_character_id = "A"
    own = s.sessions["A"]
    assert history.load_session(own.id)
    before = s.store.load_index().to_dict()
    source = s.store.session_history_path(own.id).read_bytes()
    monkeypatch.setattr(history, "switch_session", lambda session_id: False)
    assert history.continue_session(own.id) is None
    assert s.store.load_index().to_dict() == before
    assert history.get_active_session_id() == own.id
    assert s.store.session_history_path(own.id).read_bytes() == source
