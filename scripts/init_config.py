"""Create local configuration without replacing existing user files.

Run from any working directory with the project's Python environment. Starter
character data comes from the versioned XiaoYa package, never a local profile.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import yaml

from config.default_character import load_default_character


def _portable_resource_path(value):
    """Keep packaged resources relative without changing external references."""
    if not value:
        return value
    path = Path(value)
    if not path.is_absolute():
        return value
    try:
        return path.resolve().relative_to(_PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return value


def _make_resources_portable(payload):
    for field in ("avatar", "refer_audio_path"):
        if field in payload:
            payload[field] = _portable_resource_path(payload[field])
    for sprite in payload.get("sprites") or []:
        for field in ("path", "voice_path"):
            if field in sprite:
                sprite[field] = _portable_resource_path(sprite[field])
    for item in payload.get("emotion_items") or []:
        if "sprite_path" in item:
            item["sprite_path"] = _portable_resource_path(item["sprite_path"])
    return payload


def initialize(config_dir=None, *, examples_dir=None, portable_resources=False):
    """Fill missing files only; an existing ``characters.yaml: []`` stays empty.

    The source directory defaults to the repository's public examples even when
    the destination is elsewhere. ``characters.example.yaml`` is intentionally
    skipped: the full built-in persona and real sprites are loaded together.
    ``portable_resources`` writes bundled starter assets relative to the project
    so an extracted application folder can move without breaking its sprites.
    Existing configuration is never converted or overwritten.
    """
    destination_root = Path(config_dir) if config_dir is not None else _PROJECT_ROOT / "data/config"
    source_root = Path(examples_dir) if examples_dir is not None else _PROJECT_ROOT / "data/config"
    destination_root.mkdir(parents=True, exist_ok=True)
    created = []

    for example in sorted(source_root.glob("*.example.yaml")):
        destination = destination_root / example.name.replace(".example.yaml", ".yaml")
        if destination.name == "characters.yaml":
            continue
        try:
            with destination.open("xb") as output, example.open("rb") as source:
                shutil.copyfileobj(source, output)
        except FileExistsError:
            continue
        created.append(destination.name)

    character_path = destination_root / "characters.yaml"
    if not character_path.exists():
        character = load_default_character()
        payload = character.model_dump()
        if portable_resources:
            _make_resources_portable(payload)
        contents = yaml.safe_dump([payload], allow_unicode=True, sort_keys=False)
        try:
            with character_path.open("x", encoding="utf-8", newline="\n") as output:
                output.write(contents)
        except FileExistsError:
            pass
        else:
            created.append(character_path.name)
    return created


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, help="Override the local configuration directory.")
    arguments = parser.parse_args()
    created = initialize(arguments.config_dir)
    print("Created: " + ", ".join(created) if created else "Configuration already initialized; no files changed.")
