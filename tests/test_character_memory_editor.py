"""The memory manager sees all sessions while preserving stable ownership."""
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from config.schema import Character
from core.sessions.store import SessionStore
from ui.settings_ui.memory_tab import MemoryTab


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def editor(app, tmp_path, monkeypatch):
    store = SessionStore(history_root=tmp_path, sessions_dir=tmp_path / "sessions",
                         index_path=tmp_path / "sessions.json", legacy_default_file=tmp_path / "default.json")
    characters = [Character(name="同名角色", memory_id="character-a"),
                  Character(name="同名角色", memory_id="character-b")]
    first = store.create_session(title="A的聊天", character_name="同名角色", character_id="character-a")
    second = store.create_session(title="B的聊天", character_name="同名角色", character_id="character-b")
    store.set_active_session(first.id)
    # The main chat facade exposes A only; management must read the unfiltered
    # SessionStore without changing the active conversation or runtime globals.
    history = SimpleNamespace(get_memory_store=lambda: store.memory, get_session_store=lambda: store,
                              list_sessions=lambda **kwargs: store.list_sessions(character_id="character-a", **kwargs),
                              get_active_session_id=lambda: first.id)
    config = SimpleNamespace(characters=characters, api_config=SimpleNamespace(max_context_tokens=8192),
                             merged_llm_factory_kwargs=lambda: {})
    monkeypatch.setattr("core.runtime.app_runtime.try_get_app_runtime", lambda: None)
    widget = MemoryTab(config, history=history)
    yield widget, store, characters, first, second
    widget.dirty = widget._options_dirty = False
    assert widget.close_service()
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def test_editor_lists_every_character_while_main_list_is_filtered(editor):
    widget, store, _, first, second = editor
    assert [session.id for session in widget.history.list_sessions()] == [first.id]
    widget.refresh_sessions()
    assert {widget.sessions.itemData(index) for index in range(widget.sessions.count())} == {first.id, second.id}
    assert widget.characters.currentData() == ""
    assert store.memory.session(first.id)["character_id"] == "character-a"
    assert store.memory.session(second.id)["character_id"] == "character-b"
    assert store.load_index().active_session_id == first.id


def test_editor_uses_stable_ids_for_same_named_and_renamed_characters(editor):
    widget, store, characters, first, second = editor
    widget.refresh_sessions()
    assert store.memory.session(second.id)["character_id"] == characters[1].memory_id
    characters[0].name = "A改名后的名字"
    # B's historical display name now happens to equal A's new name.
    index = store.load_index()
    next(session for session in index.sessions if session.id == second.id).character_name = characters[0].name
    store.save_index(index)
    widget.refresh_sessions()
    assert store.memory.session(first.id)["character_id"] == "character-a"
    assert store.memory.session(second.id)["character_id"] == "character-b"
    assert store.get_session(second.id).character_id == "character-b"


def test_editor_claims_only_unique_legacy_names_and_preserves_unknown_records(editor):
    widget, store, characters, _, _ = editor
    unique = Character(name="唯一角色", memory_id="character-unique")
    characters.append(unique)
    claimed = store.create_session(title="旧唯一角色", character_name=unique.name)
    ambiguous = store.create_session(title="旧同名角色", character_name="同名角色")
    unknown = store.create_session(title="无归属旧记录", character_name="不在角色列表中的名字")
    unknown_path = store.session_history_path(unknown.id)
    unknown_bytes = unknown_path.read_bytes()
    widget.refresh_sessions()
    assert store.get_session(claimed.id).character_id == unique.memory_id
    assert store.memory.session(claimed.id)["character_id"] == unique.memory_id
    for session in (ambiguous, unknown):
        assert store.get_session(session.id).character_id == ""
        assert store.memory.session(session.id)["character_id"] == ""
        assert widget.sessions.findData(session.id) >= 0
    assert unknown_path.read_bytes() == unknown_bytes


def test_owned_editor_service_rejects_old_wrong_owner_before_model_call(editor, monkeypatch):
    widget, store, _, _, second = editor
    store.memory.ensure_session(second.id, "character-a")
    store.memory.sync_messages(second.id, [
        {"role": "user", "content": "记住：这是只告诉B的事"},
        {"role": "assistant", "content": "知道了"},
    ])
    widget.refresh_sessions()
    # Never silently retag an old journal: the current SessionRecord authorizes
    # extraction, and a mismatch prevents any background job/model invocation.
    assert store.memory.session(second.id)["character_id"] == "character-a"

    class NoModelCalls:
        def generate(self, *args, **kwargs):
            pytest.fail("Mismatched ownership must reject before a model call")

        def generate_stream(self, *args, **kwargs):
            pytest.fail("Mismatched ownership must reject before a model call")

    monkeypatch.setattr("llm.llm_adapter.LLMAdapterFactory.create_adapter", lambda **kwargs: NoModelCalls())
    service = widget.service()
    assert service.session_owner(second.id) == "character-b"
    assert service.session_owner("unknown-session") == ""
    assert not service.schedule(second.id, force=True)
    assert not service.extract(second.id, store.memory.session(second.id)["revision"])
    assert service.thread is None
