from __future__ import annotations

from pathlib import Path
from typing import Iterable

from core.skills.loader import build_skills_context
from core.skills.repository import SkillRepository
from core.sprite import chat_history


def _dedupe_skill_names(names: Iterable[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for name in names:
        normalized = str(name).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def resolve_effective_skill_names(
    global_default_skills: Iterable[str] | None = None,
    character_default_skills: Iterable[str] | None = None,
    session_enabled_skills: Iterable[str] | None = None,
) -> list[str]:
    return _dedupe_skill_names([
        *(global_default_skills or []),
        *(character_default_skills or []),
        *(session_enabled_skills or []),
    ])


def build_session_skills_context(
    skills_root: Path,
    global_default_skills: Iterable[str] | None = None,
    character_default_skills: Iterable[str] | None = None,
) -> str:
    active_session_id = chat_history.get_active_session_id()
    effective_skill_names: list[str] = []
    if active_session_id:
        session = chat_history.get_session_store().get_session(active_session_id)
        if session is not None:
            effective_skill_names = _dedupe_skill_names(session.enabled_skills)
    else:
        effective_skill_names = resolve_effective_skill_names(
            global_default_skills=global_default_skills,
            character_default_skills=character_default_skills,
            session_enabled_skills=None,
        )
    if not effective_skill_names:
        return ""

    repository = SkillRepository([skills_root])
    selected = []
    for skill_name in effective_skill_names:
        skill = repository.get_skill(skill_name)
        if skill is not None:
            selected.append(skill)
    return build_skills_context(selected)
