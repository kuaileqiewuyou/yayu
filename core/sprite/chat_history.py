"""聊天历史管理：保存/加载/reroll/回溯。"""
import json
from pathlib import Path
from typing import List, Dict, Optional

from core.runtime.app_runtime import try_get_app_runtime
from core.sessions.models import SessionRecord
from core.sessions.store import SessionStore
from config.atomic_io import atomic_write_text

HISTORY_DIR = Path("data/chat_history")
DEFAULT_FILE = HISTORY_DIR / "default.json"
SESSIONS_DIR = HISTORY_DIR / "sessions"
SESSIONS_INDEX_FILE = HISTORY_DIR / "sessions.json"

# UI 显示用历史
chat_history: List[Dict] = []
_active_session_id: str | None = None
_session_store = SessionStore(
    history_root=HISTORY_DIR,
    sessions_dir=SESSIONS_DIR,
    index_path=SESSIONS_INDEX_FILE,
    legacy_default_file=DEFAULT_FILE,
)


def get_history() -> List[Dict]:
    return chat_history


def get_session_store() -> SessionStore:
    return _session_store


def get_memory_store():
    return _session_store.memory


def _memory_service():
    runtime = try_get_app_runtime()
    return getattr(runtime, "memory_service", None) if runtime else None


def _active_character():
    runtime = try_get_app_runtime()
    config = getattr(runtime, "config", None) if runtime else None
    characters = getattr(config, "characters", []) or []
    if not characters:
        return None
    active_id = getattr(getattr(config, "system_config", None), "active_character_id", "")
    if active_id:
        return next((character for character in characters if getattr(character, "memory_id", "") == active_id), characters[0])
    index = getattr(config, "current_character_index", 0)
    if not isinstance(index, int) or not 0 <= index < len(characters):
        index = 0
    return characters[index]


def _character_roster():
    runtime = try_get_app_runtime()
    return getattr(getattr(runtime, "config", None), "characters", []) or []


def _session_matches_character(session: SessionRecord | None) -> bool:
    character = _active_character()
    if session is None:
        return False
    if character is None:
        return True
    if not session.character_id:
        _session_store.claim_legacy_sessions(_character_roster())
        session = _session_store.get_session(session.id)
    return bool(session and session.character_id == getattr(character, "memory_id", ""))


def sync_memory(*, turn_id=None):
    if not _active_session_id:
        return
    runtime = try_get_app_runtime()
    if not runtime:
        return
    session = _session_store.get_session(_active_session_id)
    if not _session_matches_character(session):
        return
    character = _active_character()
    character_id = getattr(character, "memory_id", "") if character else session.character_id
    store = get_memory_store()
    memory_session = store.ensure_session(_active_session_id, character_id)
    if character_id and memory_session.get("character_id") != character_id:
        return
    store.sync_messages(_active_session_id, runtime.llm_manager.get_messages(), last_turn_id=turn_id)


def configure_memory(session_id, *, mode="fresh", share_global=False):
    session = _session_store.get_session(session_id)
    if not _session_matches_character(session):
        raise ValueError("不能修改其他角色的会话记忆")
    get_memory_store().ensure_session(session_id, session.character_id)
    get_memory_store().configure(session_id, mode=mode, share_global=share_global)


def continue_session(session_id, *, title=None):
    """Copy a checkpoint as an independent story; originals stay untouched."""
    global _active_session_id
    original = _session_store.get_session(session_id)
    if not _session_matches_character(original):
        return None
    original = _session_store.get_session(session_id)
    try:
        payload = _session_store.read_session_payload(session_id, strict=True)
    except (OSError, ValueError):
        return None
    if payload.get("character_id") and payload["character_id"] != original.character_id:
        return None
    previous_id = _active_session_id
    previous_index_id = _session_store.load_index().active_session_id
    previous_history = list(chat_history)
    runtime = try_get_app_runtime()
    previous_messages = runtime.llm_manager.get_messages() if runtime else None

    def discard_copy(copy_id):
        global _active_session_id
        _session_store.delete_session(copy_id)
        index = _session_store.load_index()
        index.active_session_id = previous_index_id
        _session_store.save_index(index)
        _active_session_id = previous_id
        chat_history[:] = previous_history
        if runtime:
            runtime.llm_manager.set_messages(previous_messages)

    session = _session_store.create_session(title=title or original.title + " · 接续", character_name=original.character_name,
                                            character_id=original.character_id, make_active=False)
    try:
        _session_store.write_session_payload(session.id, payload)
        session = _session_store.update_enabled_skills(session.id, original.enabled_skills) or session
        if not switch_session(session.id):
            discard_copy(session.id)
            return None
    except (OSError, ValueError):
        discard_copy(session.id)
        return None
    return session


def set_session_store(store: SessionStore) -> None:
    global _session_store, _active_session_id
    _session_store = store
    _active_session_id = None


def get_active_session_id() -> str | None:
    return _active_session_id


def ensure_default_session(*, title: str = "默认会话", character_name: str = "") -> SessionRecord:
    global _active_session_id
    if _active_character() is not None:
        return ensure_character_session(title=title)
    index = _session_store.ensure_bootstrap_session(title=title, character_name=character_name)
    if not index.active_session_id:
        raise RuntimeError("active session was not initialized")
    _active_session_id = index.active_session_id
    session = _session_store.get_session(index.active_session_id)
    if session is None:
        raise RuntimeError("active session record missing")
    return session


def ensure_character_session(*, character_id: str | None = None, character_name: str | None = None,
                             title: str = "默认会话") -> SessionRecord:
    """Choose a character-owned session without loading or saving messages."""
    global _active_session_id
    character = _active_character()
    identity = character_id or getattr(character, "memory_id", "")
    name = character_name if character_name is not None else getattr(character, "name", "")
    existing_ids = {session.id for session in _session_store.load_index().sessions}
    session = _session_store.ensure_character_session(character_id=identity, character_name=name,
                                                       characters=_character_roster(), title=title)
    if session.id not in existing_ids:
        runtime = try_get_app_runtime()
        system = getattr(getattr(runtime, "config", None), "system_config", None)
        defaults = [*(getattr(system, "default_skills", []) or []),
                    *(getattr(character, "default_skills", []) or [])]
        enabled = list(dict.fromkeys(str(skill).strip() for skill in defaults if str(skill).strip()))
        if enabled:
            session = _session_store.update_enabled_skills(session.id, enabled) or session
    _active_session_id = session.id
    return session


def list_sessions(*, include_archived: bool = False) -> list[SessionRecord]:
    character = _active_character()
    if character is not None:
        _session_store.claim_legacy_sessions(_character_roster())
    identity = getattr(character, "memory_id", None) if character else None
    return _session_store.list_sessions(include_archived=include_archived, character_id=identity)


def create_session(*, title: str, character_name: str = "", make_active: bool = True,
                   enabled_skills: list[str] | None = None, character_id: str | None = None) -> SessionRecord:
    character = _active_character()
    identity = character_id or getattr(character, "memory_id", "")
    if character is not None and identity != getattr(character, "memory_id", ""):
        raise ValueError("不能为其他角色创建当前会话")
    session = _session_store.create_session(title=title, character_name=getattr(character, "name", character_name),
                                             character_id=identity, make_active=False)
    if enabled_skills is not None:
        session = _session_store.update_enabled_skills(session.id, enabled_skills) or session
    if make_active:
        switch_session(session.id)
    return session


def rename_session(session_id: str, title: str) -> SessionRecord | None:
    if not _session_matches_character(_session_store.get_session(session_id)):
        return None
    return _session_store.rename_session(session_id, title)


def archive_session(session_id: str, *, archived: bool = True) -> SessionRecord | None:
    if not _session_matches_character(_session_store.get_session(session_id)):
        return None
    return _session_store.archive_session(session_id, archived=archived)


def update_session_enabled_skills(session_id: str, enabled_skills: list[str]) -> SessionRecord | None:
    if not _session_matches_character(_session_store.get_session(session_id)):
        return None
    return _session_store.update_enabled_skills(session_id, enabled_skills)


def delete_session(session_id: str) -> bool:
    global _active_session_id
    deleted_session = _session_store.get_session(session_id)
    if not _session_matches_character(deleted_session):
        return False
    removed = _session_store.delete_session(session_id)
    if not removed:
        return False
    if _active_character() is not None:
        _active_session_id = ensure_character_session().id
    else:
        index = _session_store.load_index()
        _active_session_id = index.active_session_id
    if _active_session_id:
        if not load_session(_active_session_id):
            # The old active record is already gone. A corrupt fallback must
            # remain intact and must never receive the deleted transcript.
            character = _active_character()
            replacement = _session_store.create_session(
                title="默认会话", character_name=getattr(character, "name", deleted_session.character_name),
                character_id=getattr(character, "memory_id", deleted_session.character_id), make_active=False)
            load_session(replacement.id)
    else:
        chat_history.clear()
        rt = try_get_app_runtime()
        if rt:
            rt.llm_manager.clear_history()
    return True


def add_to_history(role: str, content: str, **kwargs) -> None:
    chat_history.append({"role": role, "content": content, **kwargs})


def clear_history() -> None:
    """清空当前会话历史并删除其内容文件，保留会话记录。"""
    if _active_session_id and not _session_matches_character(_session_store.get_session(_active_session_id)):
        raise ValueError("当前角色与会话不一致，已阻止清空聊天记录")
    chat_history.clear()
    rt = try_get_app_runtime()
    if rt:
        rt.llm_manager.clear_history()
    if _active_session_id:
        service = _memory_service()
        if service:
            service.cancel_session(_active_session_id)
        get_memory_store().reset(_active_session_id)
        _session_store.write_session_payload(_active_session_id, {"messages": [], "ui_history": []})
    elif DEFAULT_FILE.exists():
        DEFAULT_FILE.unlink()


def get_last_user_content() -> Optional[str]:
    """返回 UI 历史中最后一条非空用户消息内容；没有则返回 None。"""
    for entry in reversed(chat_history):
        if entry.get("role") == "user":
            content = entry.get("content")
            if isinstance(content, str) and content.strip():
                return content
    return None


def _resolve_path(filepath: Optional[str] = None) -> Path:
    if filepath:
        return Path(filepath)
    if _active_session_id:
        return _session_store.session_history_path(_active_session_id)
    return DEFAULT_FILE


def _path_matches_current_character(path: Path) -> bool:
    """Explicit file APIs must enforce ownership for known session paths too."""
    if _active_character() is None:
        return True
    resolved = path.resolve()
    for session in _session_store.load_index().sessions:
        if _session_store.session_history_path(session.id).resolve() == resolved:
            return _session_matches_character(session)
    return True


def save(filepath: Optional[str] = None) -> None:
    """保存 LLM messages + UI 历史到 JSON。"""
    if not filepath and _active_session_id and not _session_matches_character(_session_store.get_session(_active_session_id)):
        raise ValueError("当前角色与会话不一致，已阻止写入聊天记录")
    path = _resolve_path(filepath)
    if filepath and not _path_matches_current_character(path):
        raise ValueError("当前角色与会话不一致，已阻止写入聊天记录")
    path.parent.mkdir(parents=True, exist_ok=True)
    rt = try_get_app_runtime()
    data = {
        "messages": rt.llm_manager.get_messages() if rt else [],
        "ui_history": chat_history,
    }
    character = _active_character()
    if character is not None:
        data["character_id"] = character.memory_id
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))
    if not filepath and _active_session_id:
        _session_store.touch_session(_active_session_id)
        sync_memory()
        service = _memory_service()
        if service:
            service.schedule(_active_session_id)


def load(filepath: Optional[str] = None) -> bool:
    """加载历史，恢复 LLM messages 和 UI 历史。返回是否成功。"""
    if not filepath and _active_session_id and not _session_matches_character(_session_store.get_session(_active_session_id)):
        return False
    path = _resolve_path(filepath)
    if filepath and not _path_matches_current_character(path):
        return False
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError, OSError):
        return False

    # 兼容旧格式（纯 list）
    if isinstance(data, list):
        messages = data
        ui_hist = []
    elif isinstance(data, dict):
        character = _active_character()
        stored_character = data.get("character_id", "")
        if character is not None and stored_character and stored_character != character.memory_id:
            return False
        messages = data.get("messages", [])
        ui_hist = data.get("ui_history", [])
    else:
        return False
    if (not isinstance(messages, list) or not isinstance(ui_hist, list)
            or not all(isinstance(message, dict) for message in messages)
            or not all(isinstance(entry, dict) for entry in ui_hist)):
        return False

    rt = try_get_app_runtime()
    if rt:
        current_system_msgs = [m for m in rt.llm_manager.get_messages() if m.get("role") == "system"]
        history_non_system_msgs = [m for m in messages if m.get("role") != "system"]
        if current_system_msgs:
            rt.llm_manager.set_messages(current_system_msgs + history_non_system_msgs)
        else:
            rt.llm_manager.set_messages(messages)

    chat_history.clear()
    chat_history.extend(ui_hist)
    return True


def load_session(session_id: str) -> bool:
    global _active_session_id
    if not _session_matches_character(_session_store.get_session(session_id)):
        return False
    previous_id = _active_session_id
    previous_index_id = _session_store.load_index().active_session_id
    session = _session_store.set_active_session(session_id)
    if session is None:
        return False
    _active_session_id = session.id
    loaded = load()
    if loaded:
        sync_memory()
    else:
        _active_session_id = previous_id
        index = _session_store.load_index()
        index.active_session_id = previous_index_id
        _session_store.save_index(index)
    return loaded


def switch_session(session_id: str) -> bool:
    return load_session(session_id)


def pop_last_turn() -> bool:
    """Reroll：移除最后一轮（最后的 user + assistant），返回是否成功。"""
    rt = try_get_app_runtime()
    if not rt:
        return False

    msgs = rt.llm_manager.get_messages()
    last_user_idx = -1
    for i in range(len(msgs) - 1, -1, -1):
        if msgs[i]["role"] == "user":
            last_user_idx = i
            break
    if last_user_idx < 0:
        return False

    last_ui_user_idx = -1
    for i in range(len(chat_history) - 1, -1, -1):
        if chat_history[i].get("role") == "user":
            last_ui_user_idx = i
            break
    if last_ui_user_idx < 0:
        return False

    memory_turns = get_memory_store().turns(_active_session_id) if _active_session_id else []
    retried_turn_id = memory_turns[-1]["id"] if memory_turns else None
    service = _memory_service()
    if service:
        service.cancel_session(_active_session_id)
    rt.llm_manager.set_messages(msgs[:last_user_idx])
    del chat_history[last_ui_user_idx:]
    save()
    if retried_turn_id:
        get_memory_store().retain_user_turn(_active_session_id, retried_turn_id)
    return True


def revert_to(index: int) -> bool:
    """回溯到指定 user 消息索引位置。"""
    rt = try_get_app_runtime()
    if not rt:
        return False

    msgs = rt.llm_manager.get_messages()
    user_count = 0
    cut_at = -1
    for i, m in enumerate(msgs):
        if m["role"] == "user":
            if user_count == index:
                cut_at = i
                break
            user_count += 1
    if cut_at < 0:
        return False

    if _active_session_id:
        get_memory_store().forget_retained_from(_active_session_id, index)

    service = _memory_service()
    if service:
        service.cancel_session(_active_session_id)
    rt.llm_manager.set_messages(msgs[:cut_at])
    ui_user_count = 0
    ui_cut = len(chat_history)
    for i, entry in enumerate(chat_history):
        if entry.get("role") == "user":
            if ui_user_count == index:
                ui_cut = i
                break
            ui_user_count += 1
    del chat_history[ui_cut:]
    save()
    return True


def _pop_ui_from_end(role: str) -> None:
    for i in range(len(chat_history) - 1, -1, -1):
        if chat_history[i].get("role") == role:
            del chat_history[i:]
            return
