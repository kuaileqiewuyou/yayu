import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QListWidget

from config.schema import Character
from core.runtime.sprite_controller import build_sprite_map
from ui.settings_ui.character_controller import CharacterSettingsController


def _app():
    return QApplication.instance() or QApplication([])


def test_legacy_sprites_receive_persistent_ids_in_current_order():
    character = Character(
        name="诺艾尔",
        sprites=[{"path": "neutral.png"}, {"path": "happy.png"}],
    )

    assert [(sprite.id, sprite.path) for sprite in character.sprites] == [
        (0, "neutral.png"),
        (1, "happy.png"),
    ]
    assert [item["id"] for item in character.model_dump()["sprites"]] == [0, 1]


def test_prepending_new_sprite_does_not_renumber_existing_sprite_ids():
    character = Character(
        name="诺艾尔",
        sprites=[
            {"path": "new-top.png"},
            {"id": 0, "path": "neutral.png"},
            {"id": 1, "path": "happy.png"},
        ],
    )

    assert [(sprite.id, sprite.path) for sprite in character.sprites] == [
        (2, "new-top.png"),
        (0, "neutral.png"),
        (1, "happy.png"),
    ]


def test_runtime_sprite_map_uses_persistent_ids_instead_of_list_positions():
    character = Character(
        name="诺艾尔",
        sprites=[
            {"id": 2, "path": "new-top.png"},
            {"id": 0, "path": "neutral.png"},
            {"id": 1, "path": "happy.png"},
        ],
    )

    sprite_map = build_sprite_map([character], sprites_dir=Path("sprites"))

    assert sprite_map == {
        "2": str(Path("sprites") / "new-top.png"),
        "0": str(Path("sprites") / "neutral.png"),
        "1": str(Path("sprites") / "happy.png"),
    }


def test_sprite_list_displays_persistent_numbers_after_reordering():
    _app()
    window = SimpleNamespace(sprite_list=QListWidget())
    character = SimpleNamespace(
        sprites=[
            {"id": 7, "path": "new-top.png"},
            {"id": 0, "path": "neutral.png"},
            {"id": 3, "path": "angry.png"},
        ]
    )

    CharacterSettingsController(window).refresh_sprite_list_for_character(character)

    assert [window.sprite_list.item(row).text() for row in range(3)] == [
        "立绘 #08",
        "立绘 #01",
        "立绘 #04",
    ]
    assert [window.sprite_list.item(row).data(Qt.ItemDataRole.UserRole + 1) for row in range(3)] == [7, 0, 3]


def test_same_filename_imports_are_archived_without_overwriting_existing_image(tmp_path):
    first = tmp_path / "source-a" / "portrait.png"
    second = tmp_path / "source-b" / "portrait.png"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"first-image")
    second.write_bytes(b"second-image")
    characters_path = tmp_path / "config" / "characters.yaml"
    characters_path.parent.mkdir()
    window = SimpleNamespace(
        config=SimpleNamespace(_CHARACTERS_CONFIG_PATH=characters_path),
        sprite_list=QListWidget(),
    )

    archived = CharacterSettingsController(window).archive_character_sprites(
        "诺艾尔",
        [{"id": 0, "path": str(first)}, {"id": 1, "path": str(second)}],
    )

    archived_paths = [Path(item["path"]) for item in archived]
    assert [item["id"] for item in archived] == [0, 1]
    assert archived_paths[0] != archived_paths[1]
    assert archived_paths[0].read_bytes() == b"first-image"
    assert archived_paths[1].read_bytes() == b"second-image"
    assert archived_paths[1].stem.endswith("__sprite_02")
