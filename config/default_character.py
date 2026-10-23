"""Load the versioned starter character without writing user configuration."""

from pathlib import Path

import yaml

from config.schema import Character


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CHARACTER_DIRECTORY = _PROJECT_ROOT / "data" / "characters" / "xiaoya"
DEFAULT_CHARACTER_MEMORY_ID = "builtin-xiaoya"


def _resource_path(value: str) -> str:
    """Starter resources are project-relative, independent of the process cwd."""
    if not value:
        return value
    path = Path(value)
    return str((path if path.is_absolute() else _PROJECT_ROOT / path).resolve())


def load_default_character() -> Character:
    """Create a fresh, editable 小芽 from the tracked metadata and full persona.

    Absolute resource paths also bypass legacy ``data/sprites/default`` prefixing.
    The fixed identity keeps her memory stable across configuration directories.
    """
    data = yaml.safe_load((_CHARACTER_DIRECTORY / "character.yaml").read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("内置小芽角色配置必须是映射")
    data["memory_id"] = data.get("memory_id") or DEFAULT_CHARACTER_MEMORY_ID
    data["character_setting"] = (_CHARACTER_DIRECTORY / "persona.md").read_text(encoding="utf-8").strip()
    for key in ("avatar", "refer_audio_path"):
        if data.get(key):
            data[key] = _resource_path(data[key])
    for sprite in data.get("sprites") or []:
        for key in ("path", "voice_path"):
            if sprite.get(key):
                sprite[key] = _resource_path(sprite[key])
    for item in data.get("emotion_items") or []:
        if item.get("sprite_path"):
            item["sprite_path"] = _resource_path(item["sprite_path"])
    return Character.model_validate(data)
