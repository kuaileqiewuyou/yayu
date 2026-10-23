"""Character switches must never reuse another character's transcript."""
import json
from types import SimpleNamespace

import pytest
import yaml

from config.config_manager import ConfigManager
from config.schema import Character, SystemConfig
from core.runtime.app_runtime import AppRuntime, clear_app_runtime, set_app_runtime
from core.sessions.models import SessionRecord
from core.sessions.store import SessionStore
from core.sprite import chat_history


@pytest.fixture
def store(tmp_path):
    return SessionStore(history_root=tmp_path, sessions_dir=tmp_path / "sessions",
                        index_path=tmp_path / "sessions.json", legacy_default_file=tmp_path / "default.json")


@pytest.fixture
def roster():
    return [Character(name="小芽", memory_id="sprout"), Character(name="小雪", memory_id="snow")]


class FakeLLM:
    def __init__(self):
        self.messages = [{"role": "system", "content": "SPROUT_PERSONA"}]

    def get_messages(self):
        return list(self.messages)

    def set_messages(self, messages):
        self.messages = list(messages)

    def clear_history(self):
        self.messages = [message for message in self.messages if message["role"] == "system"]


@pytest.fixture
def runtime(store, roster, monkeypatch):
    clear_app_runtime()
    monkeypatch.setattr(chat_history, "_session_store", store)
    monkeypatch.setattr(chat_history, "_active_session_id", None)
    monkeypatch.setattr(chat_history, "chat_history", [])
    config = SimpleNamespace(characters=roster, system_config=SystemConfig(active_character_id="sprout"))
    runtime = AppRuntime(config=config, llm_manager=FakeLLM())
    set_app_runtime(runtime)
    yield runtime
    clear_app_runtime()


def test_old_session_record_is_readable_and_identity_round_trips():
    original = {"id": "old", "title": "旧会话", "created_at": "", "updated_at": "", "character_name": "小芽"}
    session = SessionRecord.from_dict(original)
    assert session.character_id == ""
    session.character_id = "sprout"
    assert SessionRecord.from_dict(session.to_dict()).character_id == "sprout"


def test_config_saved_identity_survives_rename_reorder_and_reload(tmp_path, monkeypatch):
    names = {"API": "api.yaml", "API_LOCAL": "api.local.yaml", "CHARACTERS": "characters.yaml",
             "SYSTEM": "system_config.yaml", "BACKGROUND": "background.yaml", "MCP": "mcp.yaml"}
    for field, filename in names.items():
        monkeypatch.setattr(ConfigManager, f"_{field}_CONFIG_PATH", tmp_path / filename)
    (tmp_path / "characters.yaml").write_text(yaml.safe_dump([
        {"name": "小芽"}, {"name": "小雪"}, {"name": "复制角色", "memory_id": "duplicate"},
        {"name": "复制角色2", "memory_id": "duplicate"}, {"name": "空白标识", "memory_id": "   "},
    ], allow_unicode=True), encoding="utf-8")
    ConfigManager.reset()
    try:
        manager = ConfigManager()
        assert manager.current_character_index == 0
        ids = [character.memory_id for character in manager.characters]
        assert len(set(ids)) == len(ids) and all(ids)
        selected_id = manager.characters[1].memory_id
        manager.system_config.active_character_id = selected_id
        manager.characters[1].name = "改名小雪"
        manager.characters.reverse()
        assert manager.current_character.name == "改名小雪"
        assert manager.current_character_index == 3
        manager.save_characters()
        manager.save_system_config()
        ConfigManager.reset()
        reloaded = ConfigManager()
        assert reloaded.current_character.memory_id == selected_id
        assert reloaded.get_character_by_id(selected_id).name == "改名小雪"
        assert reloaded.current_character_index == 3
        reloaded.system_config.active_character_id = "removed"
        assert reloaded.current_character_index == 0
    finally:
        ConfigManager.reset()


def test_same_display_name_keeps_stable_identity_transcripts_separate(store):
    roster = [Character(name="同名", memory_id="one"), Character(name="同名", memory_id="two")]
    first = store.ensure_character_session(character_id="one", character_name="同名", characters=roster)
    store.write_session_payload(first.id, {"messages": [{"role": "user", "content": "只给第一个"}], "ui_history": []})
    second = store.ensure_character_session(character_id="two", character_name="同名", characters=roster)
    assert second.id != first.id
    assert store.read_session_payload(second.id)["messages"] == []
    assert store.ensure_character_session(character_id="one", character_name="改名", characters=roster).id == first.id


def test_named_legacy_sessions_are_claimed_only_for_unique_roster_names(store, roster):
    old = store.create_session(title="旧存档", character_name="小芽")
    unknown = store.create_session(title="旧未知", character_name="已删除角色")
    original_payload = {"messages": [{"role": "assistant", "content": "不要改内容"}], "ui_history": []}
    store.write_session_payload(old.id, original_payload)
    before = store.session_history_path(old.id).read_bytes()
    selected = store.ensure_character_session(character_id="sprout", character_name="小芽", characters=roster)
    assert selected.id == old.id
    assert store.get_session(old.id).character_id == "sprout"
    assert store.get_session(unknown.id).character_id == ""
    assert store.session_history_path(old.id).read_bytes() == before


def test_duplicate_legacy_names_are_preserved_unclaimed(store):
    roster = [Character(name="同名", memory_id="one"), Character(name="同名", memory_id="two")]
    old = store.create_session(title="歧义旧记录", character_name="同名")
    first = store.ensure_character_session(character_id="one", character_name="同名", characters=roster)
    second = store.ensure_character_session(character_id="two", character_name="同名", characters=roster)
    assert old.id not in {first.id, second.id}
    assert store.get_session(old.id).character_id == ""
    assert len(store.list_sessions()) == 3


@pytest.mark.parametrize("named", [True, False])
def test_legacy_default_is_preserved_and_only_named_data_is_claimed(store, roster, named):
    payload = {"messages": [{"role": "user", "content": "历史对话"}], "ui_history": []}
    if named:
        payload["ui_history"].append({"role": "assistant", "name": "小芽", "content": "你好"})
    store.legacy_default_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before = store.legacy_default_file.read_bytes()
    selected = store.ensure_character_session(character_id="sprout", character_name="小芽", characters=roster)
    assert store.legacy_default_file.read_bytes() == before
    assert store.read_session_payload(selected.id)["messages"] == (payload["messages"] if named else [])
    assert len(store.list_sessions()) == (1 if named else 2)


def test_selects_latest_owned_session_and_avoids_archived_or_foreign(store, roster):
    first = store.create_session(title="第一", character_id="sprout")
    recent = store.create_session(title="最近", character_id="sprout")
    foreign = store.create_session(title="其他角色", character_id="snow")
    assert store.ensure_character_session(character_id="sprout", character_name="小芽", characters=roster).id == recent.id
    store.set_active_session(first.id)
    store.set_active_session(foreign.id)
    assert store.ensure_character_session(character_id="sprout", character_name="小芽", characters=roster).id == first.id
    store.archive_session(first.id)
    store.archive_session(recent.id)
    fresh = store.ensure_character_session(character_id="sprout", character_name="小芽", characters=roster)
    assert fresh.id not in {first.id, recent.id, foreign.id}


def test_runtime_switch_restores_only_own_transcript_and_current_persona(runtime, store):
    first = chat_history.ensure_character_session()
    assert chat_history.load_session(first.id)
    runtime.llm_manager.messages.append({"role": "user", "content": "只告诉小芽的秘密"})
    chat_history.add_to_history("user", "只告诉小芽的秘密")
    chat_history.save()
    runtime.config.system_config.active_character_id = "snow"
    runtime.llm_manager.messages = [{"role": "system", "content": "SNOW_PERSONA"}]
    second = chat_history.ensure_character_session()
    assert chat_history.load_session(second.id)
    assert chat_history.get_history() == []
    assert runtime.llm_manager.get_messages() == [{"role": "system", "content": "SNOW_PERSONA"}]
    runtime.llm_manager.messages.append({"role": "user", "content": "只告诉小雪的秘密"})
    chat_history.add_to_history("user", "只告诉小雪的秘密")
    chat_history.save()
    runtime.config.characters.reverse()
    runtime.config.characters[1].name = "改名小芽"
    runtime.config.system_config.active_character_id = "sprout"
    runtime.llm_manager.messages = [{"role": "system", "content": "NEW_SPROUT_PERSONA"}]
    assert chat_history.ensure_character_session().id == first.id
    assert chat_history.load_session(first.id)
    assert chat_history.get_history() == [{"role": "user", "content": "只告诉小芽的秘密"}]
    assert runtime.llm_manager.messages == [{"role": "system", "content": "NEW_SPROUT_PERSONA"},
                                            {"role": "user", "content": "只告诉小芽的秘密"}]
    assert store.memory.session(first.id)["character_id"] == "sprout"
    assert store.memory.session(second.id)["character_id"] == "snow"
    assert {session.id for session in chat_history.list_sessions()} == {first.id}


def test_cross_character_session_load_and_continue_are_rejected_without_mutation(runtime, store):
    active = chat_history.ensure_character_session()
    chat_history.load_session(active.id)
    foreign = store.create_session(title="其他角色存档", character_id="snow", make_active=False)
    before = runtime.llm_manager.get_messages()
    assert not chat_history.load_session(foreign.id)
    assert not chat_history.load(str(store.session_history_path(foreign.id)))
    with pytest.raises(ValueError):
        chat_history.save(str(store.session_history_path(foreign.id)))
    with pytest.raises(ValueError):
        chat_history.configure_memory(foreign.id, mode="character")
    assert chat_history.continue_session(foreign.id) is None
    assert chat_history.rename_session(foreign.id, "不可改名") is None
    assert chat_history.archive_session(foreign.id) is None
    assert chat_history.delete_session(foreign.id) is False
    assert chat_history.get_active_session_id() == active.id
    assert store.load_index().active_session_id == active.id
    assert runtime.llm_manager.get_messages() == before
    assert store.get_session(foreign.id).title == "其他角色存档"


def test_wrong_active_character_cannot_overwrite_or_clear_previous_history(runtime, store):
    active = chat_history.ensure_character_session()
    chat_history.load_session(active.id)
    chat_history.add_to_history("user", "小芽的记录")
    chat_history.save()
    before = store.session_history_path(active.id).read_bytes()
    runtime.config.system_config.active_character_id = "snow"
    with pytest.raises(ValueError, match="会话不一致"):
        chat_history.save()
    with pytest.raises(ValueError, match="会话不一致"):
        chat_history.clear_history()
    assert not chat_history.load_session(active.id)
    assert store.session_history_path(active.id).read_bytes() == before


def test_delete_last_owned_session_creates_clean_owned_fallback(runtime, store):
    own = chat_history.ensure_character_session()
    foreign = store.create_session(title="保留其他角色", character_id="snow", make_active=False)
    before = store.session_history_path(foreign.id).read_bytes()
    assert chat_history.delete_session(own.id)
    fallback = store.get_session(chat_history.get_active_session_id())
    assert fallback.character_id == "sprout"
    assert fallback.id != foreign.id
    assert store.session_history_path(foreign.id).read_bytes() == before


def test_created_and_continued_sessions_keep_character_identity(runtime, store):
    source = chat_history.create_session(title="自己的会话")
    assert source.character_id == "sprout" and source.character_name == "小芽"
    copied = chat_history.continue_session(source.id)
    assert copied.character_id == "sprout" and copied.id != source.id
    with pytest.raises(ValueError):
        chat_history.create_session(title="错误角色", character_id="snow")


def test_broken_payload_does_not_reassign_active_session_or_overwrite(runtime, store):
    own = chat_history.ensure_character_session()
    chat_history.load_session(own.id)
    broken = store.create_session(title="坏存档", character_id="sprout", make_active=False)
    store.session_history_path(broken.id).write_text("{broken", encoding="utf-8")
    assert not chat_history.load_session(broken.id)
    assert chat_history.get_active_session_id() == own.id
    assert store.load_index().active_session_id == own.id
    assert store.session_history_path(broken.id).read_text(encoding="utf-8") == "{broken"


def test_payload_character_binding_cannot_override_current_prompt(runtime, store):
    active = chat_history.ensure_character_session()
    chat_history.load_session(active.id)
    payload = {"character_id": "snow", "messages": [{"role": "user", "content": "外部角色秘密"}], "ui_history": []}
    foreign_file = store.history_root / "import.json"
    foreign_file.write_text(json.dumps(payload), encoding="utf-8")
    assert not chat_history.load(str(foreign_file))
    assert runtime.llm_manager.get_messages() == [{"role": "system", "content": "SPROUT_PERSONA"}]


def test_existing_wrong_memory_owner_is_not_synced_with_selected_character(runtime, store):
    session = chat_history.ensure_character_session()
    store.memory.ensure_session(session.id, "snow")
    runtime.llm_manager.messages.append({"role": "user", "content": "小芽的新信息"})
    chat_history.sync_memory()
    assert store.memory.turns(session.id) == []
    assert store.memory.session(session.id)["character_id"] == "snow"


@pytest.mark.parametrize("payload", [
    {"messages": ["broken"], "ui_history": []},
    {"messages": [], "ui_history": [None]},
    {"messages": {}, "ui_history": []},
    ["broken"],
    42,
])
def test_malformed_message_entries_fail_without_changing_current_transcript(runtime, store, payload):
    own = chat_history.ensure_character_session()
    chat_history.load_session(own.id)
    bad = store.create_session(title="结构错误存档", character_id="sprout", make_active=False)
    store.session_history_path(bad.id).write_text(json.dumps(payload), encoding="utf-8")
    assert not chat_history.load_session(bad.id)
    assert chat_history.get_active_session_id() == own.id
    assert runtime.llm_manager.get_messages() == [{"role": "system", "content": "SPROUT_PERSONA"}]


def test_delete_with_corrupt_owned_fallback_keeps_corrupt_file_and_starts_clean(runtime, store):
    own = chat_history.ensure_character_session()
    chat_history.load_session(own.id)
    runtime.llm_manager.messages.append({"role": "user", "content": "待删除旧会话"})
    chat_history.add_to_history("user", "待删除旧会话")
    broken = store.create_session(title="损坏备选", character_id="sprout", make_active=False)
    store.session_history_path(broken.id).write_text("{broken", encoding="utf-8")
    foreign = store.create_session(title="其他角色", character_id="snow", make_active=False)
    assert chat_history.delete_session(own.id)
    assert chat_history.get_active_session_id() not in {own.id, broken.id, foreign.id}
    assert chat_history.get_history() == []
    assert runtime.llm_manager.get_messages() == [{"role": "system", "content": "SPROUT_PERSONA"}]
    assert store.session_history_path(broken.id).read_text(encoding="utf-8") == "{broken"
