"""Delete explicitly removed, unreferenced managed sprites during a settings transaction."""
from pathlib import Path
from collections.abc import Iterable


def cleanup_removed_sprites(config_store, removed_paths: Iterable[str]) -> None:
    candidates = {Path(path).resolve() for path in removed_paths if path}
    if not candidates:
        return
    data_root = config_store._CHARACTERS_CONFIG_PATH.resolve().parent.parent
    sprite_root = (data_root / "sprites").resolve()
    if not sprite_root.is_relative_to(data_root):
        return
    referenced = set()

    def collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"path", "sprite_path", "avatar", "avatar_path", "refer_audio_path", "voice_path"} and isinstance(item, str) and item:
                    path = Path(item)
                    referenced.add(path.resolve())
                    if not path.is_absolute():
                        referenced.add((sprite_root / "default" / path).resolve())
                        referenced.add((sprite_root / path).resolve())
                elif isinstance(item, (dict, list)):
                    collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    # Also protect other characters, explicit avatars and scene backgrounds.
    collect(config_store.config.model_dump())
    for path in candidates - referenced:
        if path.is_relative_to(sprite_root) and path.is_file():
            path.unlink()
