"""角色立绘映射与切换辅助。"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _emotion_item_values(item: Any) -> tuple[int, str]:
    if isinstance(item, dict):
        raw_id = item.get("id", 0)
        sprite_path = item.get("sprite_path", "")
    else:
        raw_id = getattr(item, "id", 0)
        sprite_path = getattr(item, "sprite_path", "")
    try:
        item_id = int(raw_id)
    except (TypeError, ValueError):
        item_id = 0
    return item_id, str(sprite_path or "")


def _sprite_resource_path(sprite_path: str, sprites_dir: Path) -> str:
    """Support portable project paths while keeping old sprite filenames."""
    path = Path(sprite_path)
    if path.is_absolute() or (path.parts and path.parts[0] == "data"):
        return str(sprite_path)
    return str(sprites_dir / path)


def build_sprite_map(
    characters: list,
    sprites_dir: Path = Path("data/sprites/default"),
    character_index: int = 0,
) -> dict[str, str]:
    """构建情绪编号到立绘路径的映射，结构化绑定优先。"""
    sprite_map: dict[str, str] = {}
    if not characters or character_index < 0 or character_index >= len(characters):
        return sprite_map

    char = characters[character_index]
    for item in getattr(char, "emotion_items", []) or []:
        item_id, sprite_path = _emotion_item_values(item)
        key = str(item_id)
        if item_id < 1 or not sprite_path or key in sprite_map:
            continue
        sprite_map[key] = _sprite_resource_path(sprite_path, sprites_dir)

    if sprite_map:
        return sprite_map

    for i, sp in enumerate(getattr(char, "sprites", []) or []):
        if isinstance(sp, dict):
            sp_path = sp.get("path", "")
            raw_id = sp.get("id", i)
        else:
            sp_path = sp.path
            raw_id = getattr(sp, "id", i)
        try:
            sprite_id = int(raw_id) if raw_id is not None else i
        except (TypeError, ValueError):
            sprite_id = i
        if sp_path and sprite_id >= 0 and str(sprite_id) not in sprite_map:
            sprite_map[str(sprite_id)] = _sprite_resource_path(sp_path, sprites_dir)
    return sprite_map


class SpriteController:
    """封装聊天窗口立绘切换逻辑。"""

    def __init__(self, window: Any, characters: list, sprite_map: dict[str, str]) -> None:
        self.window = window
        self.characters = characters
        self.sprite_map = sprite_map
        self.character_index = 0

    def select_character(self, characters: list, character_index: int) -> None:
        """Replace both the expression map and scale when changing characters."""
        self.characters = characters
        self.character_index = character_index
        self.sprite_map = build_sprite_map(characters, character_index=character_index)
        self.show_default_sprite()

    def _scale(self) -> float:
        if 0 <= self.character_index < len(self.characters):
            return self.characters[self.character_index].sprite_scale
        return 1.0

    def set_sprite_by_id(self, asset_id: str) -> None:
        """根据 asset_id 切换立绘。"""
        if asset_id == "-1" or asset_id not in self.sprite_map:
            return
        scale = self._scale()
        self.window.set_sprite(self.sprite_map[asset_id], scale)

    def show_default_sprite(self) -> None:
        """启动时显示默认立绘。"""
        default_id = "0" if "0" in self.sprite_map else self._lowest_positive_id()
        if default_id is None:
            if callable(getattr(self.window, "clear_sprite", None)):
                self.window.clear_sprite()
            return
        scale = self._scale()
        self.window.set_sprite(self.sprite_map[default_id], scale)

    def _lowest_positive_id(self) -> str | None:
        numeric_ids = []
        for asset_id in self.sprite_map:
            try:
                value = int(asset_id)
            except (TypeError, ValueError):
                continue
            if value >= 1:
                numeric_ids.append(value)
        return str(min(numeric_ids)) if numeric_ids else None
