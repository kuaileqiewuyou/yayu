from pathlib import Path

from config.config_manager import ConfigManager
from config.schema import SkillPreset, SystemConfig


def test_system_config_accepts_named_skill_presets():
    cfg = SystemConfig.model_validate(
        {
            "default_skills": ["romance-dialogue"],
            "skill_presets": [
                {"name": "推理", "skills": ["mystery-foreshadowing"]},
                {"name": "日常", "skills": ["slice-of-life-pacing"]},
            ],
        }
    )

    assert cfg.default_skills == ["romance-dialogue"]
    assert [preset.name for preset in cfg.skill_presets] == ["推理", "日常"]
    assert cfg.skill_presets[0].skills == ["mystery-foreshadowing"]


def test_system_config_defaults_skill_presets_to_empty_list():
    cfg = SystemConfig.model_validate({})
    assert cfg.skill_presets == []


def test_config_manager_round_trips_system_skill_presets(monkeypatch, tmp_path: Path):
    config_dir = tmp_path / "data" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "api.yaml").write_text("{}\n", encoding="utf-8")
    (config_dir / "characters.yaml").write_text("[]\n", encoding="utf-8")
    (config_dir / "background.yaml").write_text("[]\n", encoding="utf-8")
    (config_dir / "system_config.yaml").write_text("{}\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    ConfigManager.reset()
    manager = ConfigManager()
    manager.system_config.default_skills = ["romance-dialogue"]
    manager.system_config.skill_presets = [
        SkillPreset(name="推理", skills=["mystery-foreshadowing"]),
        SkillPreset(name="日常", skills=["slice-of-life-pacing"]),
    ]

    manager.save_system_config()

    ConfigManager.reset()
    reloaded = ConfigManager()

    assert reloaded.system_config.default_skills == ["romance-dialogue"]
    assert [preset.name for preset in reloaded.system_config.skill_presets] == ["推理", "日常"]
    assert reloaded.system_config.skill_presets[1].skills == ["slice-of-life-pacing"]
