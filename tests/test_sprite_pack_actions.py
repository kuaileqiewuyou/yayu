"""Real Qt checks plus transactional cleanup coverage for sprite pack actions."""
from types import SimpleNamespace
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QListWidget, QTableWidget

from config.character_assets import cleanup_removed_sprites
from config.config_manager import ConfigManager
from config.schema import AppConfig, Background, Character
from ui.settings_ui.character_controller import CharacterSettingsController
from ui.settings_ui.sprite_preview import SpritePreviewDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def editor(character):
    window = SimpleNamespace(
        config=SimpleNamespace(characters=[character]), _current_character_index=0,
        sprite_list=QListWidget(), emotion_binding_table=QTableWidget(0, 4),
        _import_sprite_for_emotion_row=lambda row: None,
    )
    controller = CharacterSettingsController(window)
    controller.populate_emotion_binding_table(character)
    controller.refresh_sprite_list_for_character(character)
    return window, controller


def test_delete_unbinds_only_matching_emotions_and_preserves_ids(app, tmp_path):
    removed = tmp_path / "old.png"
    removed.write_bytes(b"source")
    character = Character(name="角色", sprites=[
        {"id": 3, "path": str(removed)}, {"id": 8, "path": "other.png"},
    ], emotion_items=[
        {"id": 1, "label": "neutral", "sprite_path": str(removed)},
        {"id": 2, "label": "happy", "sprite_path": "other.png"},
        {"id": 3, "label": "sad", "sprite_path": str(removed)},
    ])
    window, controller = editor(character)
    window.sprite_list.setCurrentRow(0)
    assert controller.delete_selected_sprite() == str(removed)
    assert controller.sprite_entries_for_character(character) == [(8, "other.png")]
    assert [row["sprite_path"] for row in controller.collect_emotion_bindings_from_table()] == ["", "other.png", ""]
    assert [controller.emotion_item_values(item)[2] for item in character.emotion_items] == ["", "other.png", ""]
    controller.import_sprite_paths_for_current_character(["new.png"])
    assert controller.collect_emotion_bindings_from_table()[0]["sprite_path"] == ""
    assert removed.read_bytes() == b"source"  # Nothing is deleted before save.
    assert controller.pending_removed_sprite_paths == {str(removed)}


def test_delete_last_sprite_and_no_selection_are_safe(app):
    character = Character(name="角色", sprites=[{"id": 4, "path": "one.png"}])
    window, controller = editor(character)
    assert controller.delete_selected_sprite() is None
    window.sprite_list.setCurrentRow(0)
    assert controller.delete_selected_sprite() == "one.png"
    assert window.sprite_list.count() == 0
    assert character.sprites == []
    assert controller.delete_selected_sprite() is None


def test_delete_duplicate_entry_keeps_shared_binding(app):
    character = Character(name="角色", sprites=[{"id": 0, "path": "same.png"}, {"id": 1, "path": "same.png"}],
                          emotion_items=[{"id": 1, "label": "neutral", "sprite_path": "same.png"}])
    window, controller = editor(character)
    window.sprite_list.setCurrentRow(0)
    controller.delete_selected_sprite()
    assert controller.collect_emotion_bindings_from_table()[0]["sprite_path"] == "same.png"


def test_delete_recognizes_legacy_import_source_binding(app, tmp_path):
    source = tmp_path / "pose.png"
    source.write_bytes(b"imported-image")
    archived = tmp_path / "data/sprites/hero/pose__sprite_03.png"
    archived.parent.mkdir(parents=True)
    archived.write_bytes(source.read_bytes())
    character = Character(name="角色", sprites=[{"id": 2, "path": str(archived)}],
                          emotion_items=[{"id": 1, "label": "neutral", "sprite_path": str(source)}])
    window, controller = editor(character)
    window.config._CHARACTERS_CONFIG_PATH = tmp_path / "data/config/characters.yaml"
    window.sprite_list.setCurrentRow(0)
    controller.delete_selected_sprite()
    assert controller.collect_emotion_bindings_from_table()[0]["sprite_path"] == ""
    assert controller.emotion_item_values(character.emotion_items[0])[2] == ""
    assert source.read_bytes() == b"imported-image"


def test_delete_does_not_unbind_same_name_with_different_content(app, tmp_path):
    source = tmp_path / "pose.png"
    source.write_bytes(b"different-image")
    archived = tmp_path / "data/sprites/hero/pose.png"
    archived.parent.mkdir(parents=True)
    archived.write_bytes(b"selected-image")
    character = Character(name="角色", sprites=[{"id": 0, "path": str(archived)}],
                          emotion_items=[{"id": 1, "label": "neutral", "sprite_path": str(source)}])
    window, controller = editor(character)
    window.config._CHARACTERS_CONFIG_PATH = tmp_path / "data/config/characters.yaml"
    window.sprite_list.setCurrentRow(0)
    controller.delete_selected_sprite()
    assert controller.collect_emotion_bindings_from_table()[0]["sprite_path"] == str(source)


def test_cleanup_only_removes_unreferenced_managed_images(tmp_path):
    root = tmp_path / "data" / "sprites"
    root.mkdir(parents=True)
    paths = {name: root / f"{name}.png" for name in ["removed", "other_role", "emotion", "avatar", "background", "unrelated"]}
    external = tmp_path / "original.png"
    for path in [*paths.values(), external]:
        path.write_bytes(b"keep")
    store = SimpleNamespace(_CHARACTERS_CONFIG_PATH=tmp_path / "data/config/characters.yaml", config=AppConfig(
        characters=[Character(name="其他角色", avatar=str(paths["avatar"]),
                              sprites=[{"path": str(paths["other_role"])}],
                              emotion_items=[{"id": 1, "label": "neutral", "sprite_path": str(paths["emotion"])}])],
        backgrounds=[Background(name="场景", sprites=[{"path": str(paths["background"])}])],
    ))
    cleanup_removed_sprites(store, [str(p) for name, p in paths.items() if name != "unrelated"] + [str(external)])
    assert not paths["removed"].exists()
    assert all(path.exists() for name, path in paths.items() if name != "removed")
    assert external.exists()


def test_cleanup_protects_relative_runtime_references(tmp_path):
    sprite = tmp_path / "data/sprites/default/shared.png"
    sprite.parent.mkdir(parents=True)
    sprite.write_bytes(b"shared")
    store = SimpleNamespace(_CHARACTERS_CONFIG_PATH=tmp_path / "data/config/characters.yaml", config=AppConfig(
        characters=[Character(name="其他角色", emotion_items=[{"id": 1, "label": "happy", "sprite_path": "shared.png"}])]))
    cleanup_removed_sprites(store, [str(sprite)])
    assert sprite.exists()


def test_cleanup_is_rolled_back_on_failure(tmp_path):
    # Use an isolated real persistence transaction without altering its singleton.
    manager = object.__new__(ConfigManager)
    config_dir = tmp_path / "data/config"
    for attr, filename in [
        ("_CHARACTERS_CONFIG_PATH", "characters.yaml"), ("_API_LOCAL_CONFIG_PATH", "api.local.yaml"),
        ("_SYSTEM_CONFIG_PATH", "system.yaml"), ("_MCP_CONFIG_PATH", "mcp.yaml"), ("_BACKGROUND_CONFIG_PATH", "background.yaml"),
    ]:
        setattr(manager, attr, config_dir / filename)
    manager._config = AppConfig()
    sprite = tmp_path / "data/sprites/old.png"
    sprite.parent.mkdir(parents=True)
    sprite.write_bytes(b"original")
    with pytest.raises(OSError, match="failed"):
        with manager.persistence_transaction():
            cleanup_removed_sprites(manager, [str(sprite)])
            assert not sprite.exists()
            raise OSError("failed")
    assert sprite.read_bytes() == b"original"


def test_preview_fit_zoom_original_and_missing_file(app, tmp_path):
    path = tmp_path / "preview.png"
    image = QImage(1200, 1800, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.red)
    assert image.save(str(path))
    dialog = SpritePreviewDialog(str(path))
    dialog.show()
    app.processEvents()
    fit_scale = dialog.view.transform().m11()
    assert 0 < fit_scale < 1
    dialog.view.zoom(1.25)
    assert dialog.view.transform().m11() == pytest.approx(fit_scale * 1.25)
    dialog.view.original_size()
    assert dialog.view.transform().m11() == 1
    assert dialog.zoom_label.text() == "100%"
    dialog.view.fit_image()
    assert dialog.view.transform().m11() < 1
    dialog.close()
    with pytest.raises(ValueError, match="无法预览"):
        SpritePreviewDialog(str(tmp_path / "missing.png"))
