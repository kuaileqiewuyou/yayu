from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.sessions.models import SessionIndex, SessionRecord
from config.atomic_io import atomic_write_text


DEFAULT_HISTORY_ROOT = Path("data/chat_history")
DEFAULT_SESSIONS_DIR = DEFAULT_HISTORY_ROOT / "sessions"
DEFAULT_INDEX_PATH = DEFAULT_HISTORY_ROOT / "sessions.json"
LEGACY_DEFAULT_FILE = DEFAULT_HISTORY_ROOT / "default.json"


class SessionStore:
    def __init__(
        self,
        *,
        history_root: Path = DEFAULT_HISTORY_ROOT,
        sessions_dir: Path = DEFAULT_SESSIONS_DIR,
        index_path: Path = DEFAULT_INDEX_PATH,
        legacy_default_file: Path = LEGACY_DEFAULT_FILE,
    ):
        self.history_root = Path(history_root)
        self.sessions_dir = Path(sessions_dir)
        self.index_path = Path(index_path)
        self.legacy_default_file = Path(legacy_default_file)
        self._memory = None

    @property
    def memory(self):
        if self._memory is None:
            from core.memory.store import MemoryStore
            self._memory = MemoryStore(self.history_root / "memory.sqlite3")
        return self._memory

    def load_index(self) -> SessionIndex:
        if not self.index_path.exists():
            return SessionIndex()
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return SessionIndex()
        if not isinstance(payload, dict):
            return SessionIndex()
        return SessionIndex.from_dict(payload)

    def save_index(self, index: SessionIndex) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(self.index_path,
            json.dumps(index.to_dict(), ensure_ascii=False, indent=2),
        )

    def ensure_bootstrap_session(self, *, title: str = "默认会话", character_name: str = "") -> SessionIndex:
        index = self.load_index()
        if index.sessions:
            if not index.active_session_id:
                index.active_session_id = index.sessions[0].id
                self.save_index(index)
            return index

        if self.legacy_default_file.exists():
            session = self.create_session_record(title=title, character_name=character_name)
            self.sessions_dir.mkdir(parents=True, exist_ok=True)
            session_path = self.session_history_path(session.id)
            session_path.write_text(self.legacy_default_file.read_text(encoding="utf-8"), encoding="utf-8")
            index = SessionIndex(active_session_id=session.id, sessions=[session])
            self.save_index(index)
            return index

        session = self.create_session_record(title=title, character_name=character_name)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.write_session_payload(session.id, {"messages": [], "ui_history": []})
        index = SessionIndex(active_session_id=session.id, sessions=[session])
        self.save_index(index)
        return index

    def create_session_record(self, *, title: str, character_name: str = "", character_id: str = "") -> SessionRecord:
        now = datetime.now().isoformat(timespec="microseconds")
        session_id = uuid4().hex
        return SessionRecord(
            id=session_id,
            title=title,
            created_at=now,
            updated_at=now,
            character_name=character_name,
            character_id=character_id,
            history_path=str(self.session_history_path(session_id).as_posix()),
        )

    def list_sessions(self, *, include_archived: bool = False, character_id: str | None = None) -> list[SessionRecord]:
        index = self.load_index()
        sessions = index.sessions
        if not include_archived:
            sessions = [session for session in sessions if not session.archived]
        if character_id is not None:
            sessions = [session for session in sessions if session.character_id == character_id]
        return sorted(sessions, key=lambda session: session.updated_at, reverse=True)

    def claim_legacy_sessions(self, characters) -> None:
        """Claim old named records only when a roster name has one owner.

        Unknown and ambiguous records remain recoverable in the index and are
        never silently attached to whichever character happens to be selected.
        """
        owners: dict[str, list[str]] = {}
        for character in characters:
            name = character.get("name", "") if isinstance(character, dict) else getattr(character, "name", "")
            identity = character.get("memory_id", "") if isinstance(character, dict) else getattr(character, "memory_id", "")
            if name and identity:
                owners.setdefault(name, []).append(identity)
        index = self.load_index()
        changed = False
        for session in index.sessions:
            candidates = owners.get(session.character_name, [])
            if not session.character_id and len(candidates) == 1:
                session.character_id = candidates[0]
                changed = True
        if changed:
            self.save_index(index)

    def _legacy_character_name(self) -> str:
        try:
            payload = json.loads(self.legacy_default_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ""
        if not isinstance(payload, dict):
            return ""
        history = payload.get("ui_history", [])
        if not isinstance(history, list):
            return ""
        names = {entry.get("name") for entry in history
                 if isinstance(entry, dict) and entry.get("role") == "assistant"
                 and isinstance(entry.get("name"), str) and entry.get("name")}
        return next(iter(names)) if len(names) == 1 else ""

    def ensure_character_session(self, *, character_id: str, character_name: str,
                                 characters=(), title: str = "默认会话") -> SessionRecord:
        """Select this character's current/recent session, or start a clean one."""
        if not character_id:
            raise ValueError("角色必须具有稳定标识")
        index = self.load_index()
        if not index.sessions and self.legacy_default_file.exists():
            self.ensure_bootstrap_session(title=title, character_name=self._legacy_character_name())
        self.claim_legacy_sessions(characters)
        index = self.load_index()
        candidates = [session for session in index.sessions
                      if session.character_id == character_id and not session.archived]
        active = next((session for session in candidates if session.id == index.active_session_id), None)
        if active is None and candidates:
            active = max(enumerate(candidates), key=lambda pair: (pair[1].updated_at, pair[0]))[1]
        if active is not None:
            self.set_active_session(active.id)
            return active
        return self.create_session(title=title, character_name=character_name,
                                   character_id=character_id, make_active=True)

    def get_session(self, session_id: str) -> SessionRecord | None:
        index = self.load_index()
        for session in index.sessions:
            if session.id == session_id:
                return session
        return None

    def session_history_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def read_session_payload(self, session_id: str, *, strict: bool = False) -> dict[str, Any]:
        path = self.session_history_path(session_id)
        if not path.exists():
            if strict:
                raise ValueError("聊天记录文件不存在")
            return {"messages": [], "ui_history": []}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            if strict:
                raise ValueError("聊天记录文件无法读取") from None
            return {"messages": [], "ui_history": []}
        if isinstance(payload, list):
            payload = {"messages": payload, "ui_history": []}
        if not isinstance(payload, dict):
            if strict:
                raise ValueError("聊天记录结构无效")
            return {"messages": [], "ui_history": []}
        payload.setdefault("messages", [])
        payload.setdefault("ui_history", [])
        if strict and any(not isinstance(payload[key], list)
                          or not all(isinstance(entry, dict) for entry in payload[key])
                          for key in ("messages", "ui_history")):
            raise ValueError("聊天记录消息结构无效")
        return payload

    def write_session_payload(self, session_id: str, payload: dict[str, Any]) -> None:
        path = self.session_history_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
        self.touch_session(session_id)

    def create_session(self, *, title: str, character_name: str = "", character_id: str = "", make_active: bool = True) -> SessionRecord:
        index = self.load_index()
        session = self.create_session_record(title=title, character_name=character_name, character_id=character_id)
        index.sessions.append(session)
        if make_active:
            index.active_session_id = session.id
        self.write_session_payload(session.id, {"messages": [], "ui_history": []})
        self.save_index(index)
        return session

    def rename_session(self, session_id: str, title: str) -> SessionRecord | None:
        index = self.load_index()
        for session in index.sessions:
            if session.id == session_id:
                session.title = title
                session.updated_at = datetime.now().isoformat(timespec="microseconds")
                self.save_index(index)
                return session
        return None

    def set_active_session(self, session_id: str) -> SessionRecord | None:
        index = self.load_index()
        for session in index.sessions:
            if session.id == session_id:
                index.active_session_id = session_id
                session.updated_at = datetime.now().isoformat(timespec="microseconds")
                self.save_index(index)
                return session
        return None

    def archive_session(self, session_id: str, *, archived: bool = True) -> SessionRecord | None:
        index = self.load_index()
        for session in index.sessions:
            if session.id == session_id:
                session.archived = archived
                session.updated_at = datetime.now().isoformat(timespec="microseconds")
                self.save_index(index)
                return session
        return None

    def update_enabled_skills(self, session_id: str, enabled_skills: list[str]) -> SessionRecord | None:
        index = self.load_index()
        for session in index.sessions:
            if session.id == session_id:
                session.enabled_skills = [str(skill) for skill in enabled_skills]
                session.updated_at = datetime.now().isoformat(timespec="microseconds")
                self.save_index(index)
                return session
        return None

    def delete_session(self, session_id: str) -> bool:
        index = self.load_index()
        before_count = len(index.sessions)
        index.sessions = [session for session in index.sessions if session.id != session_id]
        if len(index.sessions) == before_count:
            return False
        if self._memory is not None or (self.history_root / "memory.sqlite3").exists():
            self.memory.reset(session_id, delete_session=True)
        path = self.session_history_path(session_id)
        if path.exists():
            path.unlink()
        if index.active_session_id == session_id:
            index.active_session_id = index.sessions[0].id if index.sessions else None
        self.save_index(index)
        return True

    def touch_session(self, session_id: str) -> None:
        index = self.load_index()
        updated = False
        for session in index.sessions:
            if session.id == session_id:
                session.updated_at = datetime.now().isoformat(timespec="microseconds")
                updated = True
                break
        if updated:
            self.save_index(index)
