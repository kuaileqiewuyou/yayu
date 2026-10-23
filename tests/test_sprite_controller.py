from dataclasses import dataclass
from pathlib import Path

from core.runtime.sprite_controller import SpriteController, build_sprite_map


@dataclass
class FakeCharacter:
    sprites: list
    sprite_scale: float = 1.0
    emotion_items: list | None = None
    primary_sprite_path: str = ""
    emotion_tags: str = ""


class FakeWindow:
    def __init__(self):
        self.sprites = []

    def set_sprite(self, path, scale):
        self.sprites.append({"path": path, "scale": scale})


def test_build_sprite_map_returns_empty_without_characters():
    assert build_sprite_map([]) == {}


def test_build_sprite_map_supports_dict_and_object_sprites():
    characters = [
        FakeCharacter(sprites=[
            {"path": "normal.png"},
            type("Sprite", (), {"path": "happy.png"})(),
        ])
    ]

    sprite_map = build_sprite_map(characters, sprites_dir=Path("sprites"))

    assert sprite_map == {
        "0": str(Path("sprites") / "normal.png"),
        "1": str(Path("sprites") / "happy.png"),
    }


def test_build_sprite_map_supports_selected_character_index():
    characters = [
        FakeCharacter(sprites=[{"path": "first.png"}]),
        FakeCharacter(sprites=[{"path": "second.png"}, {"path": "second-happy.png"}]),
    ]

    sprite_map = build_sprite_map(characters, sprites_dir=Path("sprites"), character_index=1)

    assert sprite_map == {
        "0": str(Path("sprites") / "second.png"),
        "1": str(Path("sprites") / "second-happy.png"),
    }


def test_build_sprite_map_prefers_all_structured_emotion_bindings_over_legacy_sprites():
    characters = [
        FakeCharacter(
            sprites=[{"path": "legacy-first.png"}, {"path": "legacy-second.png"}],
            emotion_items=[
                {"id": 1, "label": "neutral", "sprite_path": "structured-default.png"},
                {"id": 2, "label": "happy", "sprite_path": "structured-happy.png"},
            ],
            primary_sprite_path="structured-default.png",
        )
    ]

    sprite_map = build_sprite_map(characters, sprites_dir=Path("sprites"))

    assert sprite_map == {
        "1": str(Path("sprites") / "structured-default.png"),
        "2": str(Path("sprites") / "structured-happy.png"),
    }


def test_build_sprite_map_can_derive_structured_default_from_emotion_items_without_primary_property():
    characters = [
        FakeCharacter(
            sprites=[{"path": "legacy-first.png"}, {"path": "legacy-second.png"}],
            emotion_items=[{"id": 1, "label": "neutral", "sprite_path": "structured-derived.png"}],
            primary_sprite_path="",
        )
    ]

    sprite_map = build_sprite_map(characters, sprites_dir=Path("sprites"))

    assert sprite_map == {
        "1": str(Path("sprites") / "structured-derived.png"),
    }


def test_build_sprite_map_keeps_structured_default_when_legacy_sprites_are_empty():
    characters = [
        FakeCharacter(
            sprites=[],
            emotion_items=[{"id": 2, "label": "happy", "sprite_path": "structured-happy.png"}],
            primary_sprite_path="",
        )
    ]

    sprite_map = build_sprite_map(characters, sprites_dir=Path("sprites"))

    assert sprite_map == {
        "2": str(Path("sprites") / "structured-happy.png"),
    }


def test_build_sprite_map_falls_back_to_legacy_first_sprite_when_no_structured_default_exists():
    characters = [
        FakeCharacter(
            sprites=[{"path": "legacy-first.png"}, {"path": "legacy-second.png"}],
            emotion_items=[{"id": 1, "label": "neutral", "sprite_path": ""}],
            primary_sprite_path="",
        )
    ]

    sprite_map = build_sprite_map(characters, sprites_dir=Path("sprites"))

    assert sprite_map == {
        "0": str(Path("sprites") / "legacy-first.png"),
        "1": str(Path("sprites") / "legacy-second.png"),
    }


def test_build_sprite_map_uses_lowest_positive_emotion_id_as_structured_default():
    characters = [
        FakeCharacter(
            sprites=[{"path": "legacy-first.png"}, {"path": "legacy-second.png"}],
            emotion_items=[
                {"id": 3, "label": "angry", "sprite_path": "structured-angry.png"},
                {"id": 2, "label": "happy", "sprite_path": "structured-happy.png"},
            ],
            primary_sprite_path="",
        )
    ]

    sprite_map = build_sprite_map(characters, sprites_dir=Path("sprites"))

    assert sprite_map == {
        "2": str(Path("sprites") / "structured-happy.png"),
        "3": str(Path("sprites") / "structured-angry.png"),
    }


def test_build_sprite_map_ignores_zero_id_structured_items_when_positive_ids_exist():
    characters = [
        FakeCharacter(
            sprites=[{"path": "legacy-first.png"}, {"path": "legacy-second.png"}],
            emotion_items=[
                {"id": 0, "label": "legacy-zero", "sprite_path": "structured-zero.png"},
                {"id": 2, "label": "happy", "sprite_path": "structured-happy.png"},
            ],
            primary_sprite_path="",
        )
    ]

    sprite_map = build_sprite_map(characters, sprites_dir=Path("sprites"))

    assert sprite_map == {
        "2": str(Path("sprites") / "structured-happy.png"),
    }


def test_build_sprite_map_falls_back_to_legacy_sprites_when_positive_ids_have_no_paths():
    characters = [
        FakeCharacter(
            sprites=[{"path": "legacy-first.png"}, {"path": "legacy-second.png"}],
            emotion_items=[
                {"id": 2, "label": "happy", "sprite_path": ""},
                {"id": 3, "label": "angry", "sprite_path": ""},
            ],
            primary_sprite_path="",
        )
    ]

    sprite_map = build_sprite_map(characters, sprites_dir=Path("sprites"))

    assert sprite_map == {
        "0": str(Path("sprites") / "legacy-first.png"),
        "1": str(Path("sprites") / "legacy-second.png"),
    }


def test_build_sprite_map_ignores_legacy_zero_emotion_tags_when_positive_structured_default_exists():
    characters = [
        FakeCharacter(
            sprites=[{"path": "legacy-first.png"}, {"path": "legacy-second.png"}],
            emotion_items=[{"id": 2, "label": "happy", "sprite_path": "structured-happy.png"}],
            primary_sprite_path="",
            emotion_tags="0: legacy-zero\\n2: happy",
        )
    ]

    sprite_map = build_sprite_map(characters, sprites_dir=Path("sprites"))

    assert sprite_map == {
        "2": str(Path("sprites") / "structured-happy.png"),
    }


def test_build_sprite_map_keeps_first_valid_binding_for_duplicate_structured_id():
    characters = [
        FakeCharacter(
            sprites=[{"path": "legacy.png"}],
            emotion_items=[
                {"id": 2, "label": "happy", "sprite_path": "first.png"},
                {"id": 2, "label": "duplicate", "sprite_path": "second.png"},
            ],
        )
    ]

    assert build_sprite_map(characters, sprites_dir=Path("sprites")) == {
        "2": str(Path("sprites") / "first.png"),
    }


def test_set_sprite_by_id_sets_known_sprite_with_character_scale():
    window = FakeWindow()
    characters = [FakeCharacter(sprites=[], sprite_scale=1.5)]
    controller = SpriteController(window, characters, {"2": "sprite.png"})

    controller.set_sprite_by_id("2")

    assert window.sprites == [{"path": "sprite.png", "scale": 1.5}]


def test_set_sprite_by_id_ignores_unknown_and_negative_asset_id():
    window = FakeWindow()
    characters = [FakeCharacter(sprites=[], sprite_scale=1.5)]
    controller = SpriteController(window, characters, {"2": "sprite.png"})

    controller.set_sprite_by_id("-1")
    controller.set_sprite_by_id("9")

    assert window.sprites == []


def test_set_sprite_by_id_defaults_scale_without_characters():
    window = FakeWindow()
    controller = SpriteController(window, [], {"0": "sprite.png"})

    controller.set_sprite_by_id("0")

    assert window.sprites == [{"path": "sprite.png", "scale": 1.0}]


def test_show_default_sprite_sets_asset_zero():
    window = FakeWindow()
    characters = [FakeCharacter(sprites=[], sprite_scale=2.0)]
    controller = SpriteController(window, characters, {"0": "default.png"})

    controller.show_default_sprite()

    assert window.sprites == [{"path": "default.png", "scale": 2.0}]


def test_show_default_sprite_uses_lowest_positive_structured_id_without_zero():
    window = FakeWindow()
    characters = [FakeCharacter(sprites=[], sprite_scale=1.25)]
    controller = SpriteController(window, characters, {"3": "third.png", "1": "first.png"})

    controller.show_default_sprite()

    assert window.sprites == [{"path": "first.png", "scale": 1.25}]


def test_show_default_sprite_uses_only_available_positive_id():
    window = FakeWindow()
    characters = [FakeCharacter(sprites=[], sprite_scale=2.0)]
    controller = SpriteController(window, characters, {"9": "other.png"})

    controller.show_default_sprite()

    assert window.sprites == [{"path": "other.png", "scale": 2.0}]
