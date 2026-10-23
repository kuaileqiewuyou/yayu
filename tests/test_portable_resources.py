"""Portable first-run resources survive extraction and folder relocation."""

from pathlib import Path
import shutil
from types import SimpleNamespace

from PySide6.QtGui import QImage
import pytest
import yaml

from config import default_character
from config.schema import Character
from core.runtime.sprite_controller import build_sprite_map
from scripts import init_config


@pytest.fixture
def starter_package(tmp_path, monkeypatch):
    source_root = Path(__file__).resolve().parents[1]
    package = tmp_path / "first extraction"
    resources = [
        "data/characters/xiaoya/README.md",
        "data/characters/xiaoya/character.yaml",
        "data/characters/xiaoya/persona.md",
        "data/characters/xiaoya/standing-neutral.png",
        "data/characters/xiaoya/standing-wink.png",
        "data/characters/xiaoya/standing-listening.png",
        "ui/assets/yayu.png",
    ]
    for relative in resources:
        destination = package / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_root / relative, destination)
    (package / "data/config").mkdir(parents=True)
    monkeypatch.setattr(init_config, "_PROJECT_ROOT", package)
    monkeypatch.setattr(default_character, "_PROJECT_ROOT", package)
    monkeypatch.setattr(default_character, "_CHARACTER_DIRECTORY", package / "data/characters/xiaoya")
    return package


def test_portable_initialization_contains_only_relative_packaged_resource_paths(starter_package):
    assert init_config.initialize(portable_resources=True) == ["characters.yaml"]

    text = (starter_package / "data/config/characters.yaml").read_text(encoding="utf-8")
    character = yaml.safe_load(text)[0]
    assert str(starter_package) not in text
    assert starter_package.as_posix() not in text
    assert character["avatar"] == "ui/assets/yayu.png"
    assert character["refer_audio_path"] == ""
    assert character["memory_id"] == "builtin-xiaoya"
    assert len(character["character_setting"]) > 1000
    expected = [
        "data/characters/xiaoya/standing-neutral.png",
        "data/characters/xiaoya/standing-wink.png",
        "data/characters/xiaoya/standing-listening.png",
    ]
    assert [sprite["path"] for sprite in character["sprites"]] == expected
    assert [item["sprite_path"] for item in character["emotion_items"]] == expected


def test_all_starter_sprites_decode_after_package_relocation(starter_package, tmp_path, monkeypatch):
    init_config.initialize(portable_resources=True)
    relocated = tmp_path / "移动后 package"
    shutil.copytree(starter_package, relocated)
    monkeypatch.chdir(relocated)

    character = Character.model_validate(yaml.safe_load(
        Path("data/config/characters.yaml").read_text(encoding="utf-8")
    )[0])
    sprites = build_sprite_map([character])

    assert set(sprites) == {"1", "2", "3"}
    assert Path(character.avatar).resolve().is_relative_to(relocated)
    assert not QImage(character.avatar).isNull()
    for path in sprites.values():
        assert Path(path).resolve().is_relative_to(relocated)
        image = QImage(path)
        assert not image.isNull(), path
        assert (image.width(), image.height()) == (1024, 1536)


def test_portable_conversion_covers_audio_fields_and_preserves_external_paths(starter_package, tmp_path, monkeypatch):
    character = default_character.load_default_character()
    character.refer_audio_path = str(starter_package / "data/voices/reference.wav")
    character.sprites[0].voice_path = str(starter_package / "data/voices/neutral.wav")
    external_voice = str(tmp_path / "external" / "voice.wav")
    character.sprites[1].voice_path = external_voice
    character.sprites[2].voice_path = "data/voices/already-relative.wav"
    monkeypatch.setattr(init_config, "load_default_character", lambda: character)

    init_config.initialize(portable_resources=True)

    payload = yaml.safe_load((starter_package / "data/config/characters.yaml").read_text(encoding="utf-8"))[0]
    assert payload["refer_audio_path"] == "data/voices/reference.wav"
    assert payload["sprites"][0]["voice_path"] == "data/voices/neutral.wav"
    assert payload["sprites"][1]["voice_path"] == external_voice
    assert payload["sprites"][2]["voice_path"] == "data/voices/already-relative.wav"
    # Conversion only changes the serialized payload, not the loaded character.
    assert Path(character.refer_audio_path).is_absolute()


@pytest.mark.parametrize("original", [
    b"[]\r\n",
    "# 保留自定义角色\r\n- name: 本地角色\r\n  avatar: custom.png\r\n".encode("utf-8"),
    b"# blank configuration remains intentional\n",
])
def test_portable_initialization_never_rewrites_existing_characters(starter_package, original):
    path = starter_package / "data/config/characters.yaml"
    path.write_bytes(original)

    assert init_config.initialize(portable_resources=True) == []
    assert path.read_bytes() == original


@pytest.mark.parametrize("structured", [True, False])
def test_sprite_mapping_keeps_absolute_and_project_paths_and_prefixes_legacy_filenames(tmp_path, structured):
    absolute = str(tmp_path / "external-sprite.png")
    paths = [absolute, "data/characters/xiaoya/standing-wink.png", "normal.png"]
    character = SimpleNamespace(
        emotion_items=[{"id": index, "sprite_path": path} for index, path in enumerate(paths, 1)] if structured else [],
        sprites=[{"id": index, "path": path} for index, path in enumerate(paths, 1)],
    )
    legacy_root = Path("legacy-sprites")

    assert build_sprite_map([character], sprites_dir=legacy_root) == {
        "1": absolute,
        "2": paths[1],
        "3": str(legacy_root / "normal.png"),
    }
