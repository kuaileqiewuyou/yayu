from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionRecord:
    id: str
    title: str
    created_at: str
    updated_at: str
    character_name: str = ""
    archived: bool = False
    history_path: str = ""
    enabled_skills: list[str] = field(default_factory=list)
    character_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "character_name": self.character_name,
            "character_id": self.character_id,
            "archived": self.archived,
            "history_path": self.history_path,
            "enabled_skills": list(self.enabled_skills),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SessionRecord":
        return cls(
            id=str(payload.get("id", "")),
            title=str(payload.get("title", "")),
            created_at=str(payload.get("created_at", "")),
            updated_at=str(payload.get("updated_at", "")),
            character_name=str(payload.get("character_name", "")),
            character_id=str(payload.get("character_id") or ""),
            archived=bool(payload.get("archived", False)),
            history_path=str(payload.get("history_path", "")),
            enabled_skills=[str(item) for item in payload.get("enabled_skills", [])],
        )


@dataclass
class SessionIndex:
    active_session_id: str | None = None
    sessions: list[SessionRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_session_id": self.active_session_id,
            "sessions": [session.to_dict() for session in self.sessions],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SessionIndex":
        raw_sessions = payload.get("sessions", [])
        sessions = [SessionRecord.from_dict(item) for item in raw_sessions if isinstance(item, dict)]
        active_session_id = payload.get("active_session_id")
        if active_session_id is not None:
            active_session_id = str(active_session_id)
        return cls(active_session_id=active_session_id, sessions=sessions)
