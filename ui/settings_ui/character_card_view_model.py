from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CharacterCardViewModel:
    name: str
    avatar_text: str
    avatar_source: str
    stats_text: str


def _sprite_path(sprite: Any) -> str:
    if isinstance(sprite, dict):
        return str(sprite.get("path", "") or "")
    return str(getattr(sprite, "path", "") or "")


def character_card_avatar_source(character: Any) -> str:
    explicit_avatar = getattr(character, "avatar", "") or getattr(character, "avatar_path", "")
    if explicit_avatar:
        return str(explicit_avatar)

    primary_sprite_path = getattr(character, "primary_sprite_path", "") or ""
    if primary_sprite_path:
        return str(primary_sprite_path)

    for sprite in getattr(character, "sprites", []) or []:
        first_path = _sprite_path(sprite)
        if first_path:
            return first_path

    return ""


def character_card_stats_text(character: Any) -> str:
    sprite_count = len(getattr(character, "sprites", []) or [])
    emotion_count = len(getattr(character, "emotion_items", []) or [])
    return f"{sprite_count} 张立绘 · {emotion_count} 个情绪"


def build_character_card_view_model(character: Any, *, placeholder_text: str = "头像") -> CharacterCardViewModel:
    return CharacterCardViewModel(
        name=str(getattr(character, "name", "") or ""),
        avatar_text=placeholder_text,
        avatar_source=character_card_avatar_source(character),
        stats_text=character_card_stats_text(character),
    )
