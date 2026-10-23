import json
from pathlib import Path

from core.sessions.store import SessionStore


def test_session_store_bootstraps_default_session(tmp_path):
    store = SessionStore(
        history_root=tmp_path,
        sessions_dir=tmp_path / "sessions",
        index_path=tmp_path / "sessions.json",
        legacy_default_file=tmp_path / "default.json",
    )

    index = store.ensure_bootstrap_session(title="默认会话", character_name="诺艾尔")

    assert index.active_session_id is not None
    assert len(index.sessions) == 1
    session = index.sessions[0]
    assert session.title == "默认会话"
    payload = store.read_session_payload(session.id)
    assert payload == {"messages": [], "ui_history": []}


def test_session_store_migrates_legacy_default_file(tmp_path):
    legacy_file = tmp_path / "default.json"
    legacy_file.write_text(json.dumps({"messages": [{"role": "user", "content": "你好"}], "ui_history": []}, ensure_ascii=False), encoding="utf-8")
    store = SessionStore(
        history_root=tmp_path,
        sessions_dir=tmp_path / "sessions",
        index_path=tmp_path / "sessions.json",
        legacy_default_file=legacy_file,
    )

    index = store.ensure_bootstrap_session(title="迁移会话")
    session = index.sessions[0]
    payload = store.read_session_payload(session.id)

    assert payload["messages"][0]["content"] == "你好"


def test_session_store_create_switch_rename_delete(tmp_path):
    store = SessionStore(
        history_root=tmp_path,
        sessions_dir=tmp_path / "sessions",
        index_path=tmp_path / "sessions.json",
        legacy_default_file=tmp_path / "default.json",
    )
    store.ensure_bootstrap_session(title="默认会话")

    created = store.create_session(title="第二会话", character_name="诺艾尔", make_active=True)
    assert store.load_index().active_session_id == created.id

    renamed = store.rename_session(created.id, "第二会话-重命名")
    assert renamed is not None
    assert renamed.title == "第二会话-重命名"

    first = store.list_sessions(include_archived=True)[-1]
    switched = store.set_active_session(first.id)
    assert switched is not None
    assert store.load_index().active_session_id == first.id

    assert store.delete_session(created.id) is True
    assert store.get_session(created.id) is None
