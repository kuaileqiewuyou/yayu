"""Resolve the selected character without changing the character list order."""
from __future__ import annotations

from typing import Any


def get_active_character_index(config: Any) -> int:
    characters = getattr(config, "characters", []) or []
    if not characters:
        return -1
    identity = getattr(getattr(config, "system_config", None), "active_character_id", "")
    if identity:
        matches = [i for i, character in enumerate(characters)
                   if getattr(character, "memory_id", "") == identity]
        if len(matches) == 1:
            return matches[0]
    index = getattr(config, "current_character_index", 0)
    return index if isinstance(index, int) and 0 <= index < len(characters) else 0


def get_active_character(config: Any) -> Any | None:
    index = get_active_character_index(config)
    return config.characters[index] if index >= 0 else None


def character_choices(config: Any) -> list[dict[str, str]]:
    return [
        {"id": character.memory_id, "memory_id": character.memory_id, "name": character.name,
         "avatar": str(getattr(character, "avatar", "") or "")}
        for character in getattr(config, "characters", [])
        if getattr(character, "memory_id", "")
    ]
