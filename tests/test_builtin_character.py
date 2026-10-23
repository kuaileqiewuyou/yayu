import json
from pathlib import Path

import pytest
import yaml

from config import default_character
from config.config_manager import ConfigManager
from core.runtime.sprite_controller import build_sprite_map


@pytest.fixture
def starter_store(tmp_path, monkeypatch):
    """Keep every configuration path and the starter fixture outside user data."""
    project_root = tmp_path / "project"
    profile_root = project_root / "data" / "characters" / "xiaoya"
    profile_root.mkdir(parents=True)
    asset_path = project_root / "ui" / "assets" / "xiaoya.png"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(b"fixture image")
    (profile_root / "character.yaml").write_text(yaml.safe_dump({
        "name": "小芽",
        "color": "#718772",
        "avatar": "ui/assets/xiaoya.png",
        "sprites": [{"id": 0, "path": "ui/assets/xiaoya.png"}],
        "emotion_items": [{"id": 1, "label": "眨眼微笑", "sprite_path": "ui/assets/xiaoya.png"}],
        "default_skills": [],
    }, allow_unicode=True), encoding="utf-8")
    persona = "# 小芽\n\n薄荷绿短发的原创桌面伙伴。\n\n## 相处方式\n先听完，再一起解决问题。"
    (profile_root / "persona.md").write_text(persona + "\n", encoding="utf-8")
    config_root = tmp_path / "user-data" / "config"
    config_root.mkdir(parents=True)
    for stem, filename in (
        ("API_CONFIG", "api.yaml"),
        ("API_LOCAL_CONFIG", "api.local.yaml"),
        ("SYSTEM_CONFIG", "system_config.yaml"),
        ("CHARACTERS_CONFIG", "characters.yaml"),
        ("BACKGROUND_CONFIG", "background.yaml"),
        ("MCP_CONFIG", "mcp.yaml"),
    ):
        monkeypatch.setattr(ConfigManager, f"_{stem}_PATH", config_root / filename)
    monkeypatch.setattr(default_character, "_PROJECT_ROOT", project_root)
    monkeypatch.setattr(default_character, "_CHARACTER_DIRECTORY", profile_root)
    unrelated_cwd = tmp_path / "unrelated-cwd"
    unrelated_cwd.mkdir()
    monkeypatch.chdir(unrelated_cwd)
    ConfigManager.reset()
    yield {"config_root": config_root, "asset_path": asset_path, "persona": persona}
    ConfigManager.reset()


def test_first_run_loads_complete_starter_from_project_resources_without_writing(starter_store):
    manager = ConfigManager()

    assert len(manager.characters) == 1
    character = manager.characters[0]
    assert character.name == "小芽"
    assert character.memory_id == default_character.DEFAULT_CHARACTER_MEMORY_ID
    assert character.character_setting == starter_store["persona"]
    assert character.avatar == str(starter_store["asset_path"].resolve())
    assert character.primary_sprite_path == character.avatar
    assert build_sprite_map(manager.characters) == {"1": character.avatar}
    assert Path(character.avatar).is_file()
    assert list(starter_store["config_root"].iterdir()) == []


@pytest.mark.parametrize("content", ["", "# 尚未配置角色\n", "null\n", "{}\n"])
def test_uninitialized_character_document_loads_starter(starter_store, content):
    characters_path = starter_store["config_root"] / "characters.yaml"
    characters_path.write_text(content, encoding="utf-8")

    assert [character.name for character in ConfigManager().characters] == ["小芽"]
    assert characters_path.read_text(encoding="utf-8") == content


def test_explicitly_saved_empty_list_stays_empty(starter_store):
    characters_path = starter_store["config_root"] / "characters.yaml"
    characters_path.write_text("[]\n", encoding="utf-8")

    assert ConfigManager().characters == []
    assert characters_path.read_text(encoding="utf-8") == "[]\n"


def test_existing_character_order_settings_and_identity_are_preserved(starter_store):
    characters_path = starter_store["config_root"] / "characters.yaml"
    original = yaml.safe_dump([
        {"name": "自定义角色", "memory_id": "keep-first", "character_setting": "原本设定", "avatar": "custom.png"},
        {"name": "第二位", "memory_id": "keep-second"},
    ], allow_unicode=True)
    characters_path.write_text(original, encoding="utf-8")

    characters = ConfigManager().characters

    assert [character.name for character in characters] == ["自定义角色", "第二位"]
    assert [character.memory_id for character in characters] == ["keep-first", "keep-second"]
    assert characters[0].character_setting == "原本设定"
    assert characters[0].avatar == "custom.png"
    assert characters_path.read_text(encoding="utf-8") == original


def test_starter_edits_save_and_reload_without_resetting_persona_or_memory(starter_store):
    manager = ConfigManager()
    memory_id = manager.characters[0].memory_id
    manager.characters[0].name = "我的小芽"
    manager.characters[0].character_setting += "\n喜欢乌龙茶。"
    expected_persona = manager.characters[0].character_setting
    manager.save_characters()
    ConfigManager.reset()

    character = ConfigManager().characters[0]

    assert character.name == "我的小芽"
    assert character.memory_id == memory_id
    assert character.character_setting == expected_persona
    assert character.avatar == str(starter_store["asset_path"].resolve())


def test_deleting_starter_and_saving_does_not_resurrect_it(starter_store):
    manager = ConfigManager()
    manager.characters.clear()
    manager.save_characters()
    ConfigManager.reset()

    assert ConfigManager().characters == []


def test_starter_loads_are_independent_and_keep_same_identity(starter_store):
    first = default_character.load_default_character()
    first.character_setting = "本次编辑"
    first.emotion_items.clear()

    second = default_character.load_default_character()

    assert second.memory_id == first.memory_id
    assert second.character_setting == starter_store["persona"]
    assert len(second.emotion_items) == 1


def test_starter_persona_reaches_runtime_system_prompt_without_model_request(starter_store, monkeypatch):
    from core.runtime import llm_setup

    class OfflineAdapter:
        def chat(self, *args, **kwargs):
            raise AssertionError("初始化角色不应调用模型")

    monkeypatch.setattr(llm_setup.LLMAdapterFactory, "create_adapter", lambda **kwargs: OfflineAdapter())
    monkeypatch.setattr(llm_setup, "build_session_skills_context", lambda *args, **kwargs: "")

    context = llm_setup.create_llm_runtime_context(ConfigManager())

    assert context.active_character_name == "小芽"
    assert context.active_character_color == "#718772"
    assert starter_store["persona"] in context.manager.user_template
    assert 'character_name 必须固定填写 "小芽"' in context.manager.user_template


@pytest.fixture
def real_starter_store(tmp_path, monkeypatch):
    """Use the tracked starter while isolating all application persistence."""
    config_root = tmp_path / "config"
    for stem, filename in (
        ("API_CONFIG", "api.yaml"),
        ("API_LOCAL_CONFIG", "api.local.yaml"),
        ("SYSTEM_CONFIG", "system_config.yaml"),
        ("CHARACTERS_CONFIG", "characters.yaml"),
        ("BACKGROUND_CONFIG", "background.yaml"),
        ("MCP_CONFIG", "mcp.yaml"),
    ):
        monkeypatch.setattr(ConfigManager, f"_{stem}_PATH", config_root / filename)
    monkeypatch.chdir(tmp_path)
    ConfigManager.reset()
    yield config_root
    ConfigManager.reset()


def test_real_xiaoya_package_loads_images_and_valid_prompt_from_another_cwd(real_starter_store, qapp):
    from PySide6 import QtSvg  # noqa: F401 - register the SVG image plugin
    from PySide6.QtGui import QPixmap

    from llm.template_generator import generate_system_prompt

    manager = ConfigManager()
    character = manager.characters[0]
    assert character.name == "小芽"
    assert character.memory_id == "builtin-xiaoya"
    persona_path = default_character._CHARACTER_DIRECTORY / "persona.md"
    assert character.character_setting == persona_path.read_text(encoding="utf-8").strip()
    assert len(character.character_setting) > 1000
    avatar = QPixmap(character.avatar)
    assert not avatar.isNull()
    sprite_map = build_sprite_map(manager.characters)
    expected_sprites = {
        "1": "standing-neutral.png",
        "2": "standing-wink.png",
        "3": "standing-listening.png",
    }
    assert sprite_map == {
        sprite_id: str(default_character._CHARACTER_DIRECTORY / filename)
        for sprite_id, filename in expected_sprites.items()
    }
    assert character.primary_sprite_path == sprite_map["1"]
    for sprite_path in sprite_map.values():
        portrait = QPixmap(sprite_path)
        assert not portrait.isNull(), sprite_path
        assert portrait.hasAlphaChannel(), sprite_path
        assert portrait.height() > portrait.width(), sprite_path

    prompt = generate_system_prompt(character)
    assert character.character_setting in prompt
    assert 'character_name 必须固定填写 "小芽"' in prompt
    examples = prompt.split("【示例输出】", 1)[1].split("【重要规则】", 1)[0]
    example_objects = [json.loads(line) for line in examples.splitlines() if line.startswith('{"')]
    assert example_objects
    assert {item["sprite"] for item in example_objects} == {"1", "-1"}
    assert not real_starter_store.exists()


def test_real_xiaoya_can_be_saved_edited_and_reloaded_without_reset(real_starter_store):
    manager = ConfigManager()
    original_character = manager.characters[0]
    original_character.character_setting += "\n测试保存的个性化设定。"
    expected = original_character.model_dump()
    manager.save_characters()
    ConfigManager.reset()

    assert ConfigManager().characters[0].model_dump() == expected
    assert ConfigManager().characters[0].memory_id == "builtin-xiaoya"
