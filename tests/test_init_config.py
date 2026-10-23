"""Initialization uses the public starter and never rewrites local profiles."""

from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from config.config_manager import ConfigManager
from config.default_character import load_default_character
from scripts import init_config


@pytest.fixture
def isolated_configuration(tmp_path, monkeypatch):
    destination = tmp_path / "local" / "config"
    for attribute, filename in (
        ("_API_CONFIG_PATH", "api.yaml"),
        ("_API_LOCAL_CONFIG_PATH", "api.local.yaml"),
        ("_SYSTEM_CONFIG_PATH", "system_config.yaml"),
        ("_CHARACTERS_CONFIG_PATH", "characters.yaml"),
        ("_BACKGROUND_CONFIG_PATH", "background.yaml"),
        ("_MCP_CONFIG_PATH", "mcp.yaml"),
    ):
        monkeypatch.setattr(ConfigManager, attribute, destination / filename)
    ConfigManager.reset()
    yield destination
    ConfigManager.reset()


@pytest.fixture
def public_examples(tmp_path):
    source = tmp_path / "public-examples"
    source.mkdir()
    (source / "system_config.example.yaml").write_text("always_on_top: false\n", encoding="utf-8")
    (source / "background.example.yaml").write_text("[]\n", encoding="utf-8")
    (source / "mcp.example.yaml").write_text("mcp_servers: []\n", encoding="utf-8")
    # Old public examples must not replace the full built-in character.
    (source / "characters.example.yaml").write_text("- name: 示例角色\n", encoding="utf-8")
    return source


def test_first_run_creates_complete_starter_and_public_defaults(isolated_configuration, public_examples):
    destination = isolated_configuration

    created = init_config.initialize(destination, examples_dir=public_examples)

    assert set(created) == {"system_config.yaml", "background.yaml", "mcp.yaml", "characters.yaml"}
    for source in public_examples.glob("*.example.yaml"):
        if source.name != "characters.example.yaml":
            assert (destination / source.name.replace(".example.yaml", ".yaml")).read_bytes() == source.read_bytes()
    expected = load_default_character()
    characters = yaml.safe_load((destination / "characters.yaml").read_text(encoding="utf-8"))
    assert characters == [expected.model_dump()]
    assert len(characters[0]["character_setting"]) > 1000
    assert len(characters[0]["emotion_items"]) == 3
    assert all(Path(item["sprite_path"]).is_file() for item in characters[0]["emotion_items"])
    assert ConfigManager().characters[0].model_dump() == expected.model_dump()
    assert not (destination / "api.local.yaml").exists()


@pytest.mark.parametrize("original", [
    "[]\n",
    "# 保留我的配置\n- name: 自定义角色\n  memory_id: stable-local-id\n  character_setting: 我的原创设定\n",
    "# 空白文件也不应被初始化器覆盖\n",
])
def test_existing_character_file_is_preserved_byte_for_byte(isolated_configuration, public_examples, original):
    destination = isolated_configuration
    destination.mkdir(parents=True)
    character_path = destination / "characters.yaml"
    character_path.write_bytes(original.encode("utf-8"))

    created = init_config.initialize(destination, examples_dir=public_examples)

    assert "characters.yaml" not in created
    assert character_path.read_bytes() == original.encode("utf-8")
    if original == "[]\n":
        assert ConfigManager().characters == []
    elif "stable-local-id" in original:
        assert ConfigManager().characters[0].memory_id == "stable-local-id"
        assert ConfigManager().characters[0].character_setting == "我的原创设定"


def test_second_run_preserves_all_files_including_local_api_overlay(isolated_configuration, public_examples):
    destination = isolated_configuration
    init_config.initialize(destination, examples_dir=public_examples)
    local_api = destination / "api.local.yaml"
    local_api.write_text("llm_api_key: {}\n# 本机覆盖文件\n", encoding="utf-8")
    (destination / "system_config.yaml").write_text("always_on_top: true\n", encoding="utf-8")
    before = {path.name: path.read_bytes() for path in destination.iterdir()}

    assert init_config.initialize(destination, examples_dir=public_examples) == []
    assert {path.name: path.read_bytes() for path in destination.iterdir()} == before


def test_cli_from_unrelated_cwd_uses_packaged_examples_and_real_starter(tmp_path):
    destination = tmp_path / "configuration"
    unrelated_cwd = tmp_path / "elsewhere"
    unrelated_cwd.mkdir()
    result = subprocess.run(
        [sys.executable, str(Path(init_config.__file__).resolve()), "--config-dir", str(destination)],
        cwd=unrelated_cwd, capture_output=True, text=True, encoding="utf-8", check=False,
    )

    assert result.returncode == 0, result.stderr
    character = yaml.safe_load((destination / "characters.yaml").read_text(encoding="utf-8"))[0]
    assert character["name"] == "小芽"
    assert character["character_setting"] == load_default_character().character_setting
    expected_examples = [
        path for path in (init_config._PROJECT_ROOT / "data/config").glob("*.example.yaml")
        if path.name != "characters.example.yaml"
    ]
    assert expected_examples, "公开发布包需要包含首次初始化用的配置样例"
    for source in expected_examples:
        assert (destination / source.name.replace(".example.yaml", ".yaml")).read_bytes() == source.read_bytes()
