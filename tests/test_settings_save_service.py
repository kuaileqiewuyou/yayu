"""Focused tests for SettingsWindow save/apply extraction helpers."""
from __future__ import annotations

import ast
import importlib
from copy import deepcopy
from pathlib import Path

import pytest

from config.schema import ApiConfig, AppConfig, Background, Character, SystemConfig


class _Combo:
    def __init__(self, value: str, options: list[str] | None = None):
        self._value = value
        self._options = options or []

    def currentText(self) -> str:
        return self._value

    def currentData(self):
        return self._value

    def findData(self, value):
        return self.findText(value)

    def findText(self, value: str) -> int:
        try:
            return self._options.index(value)
        except ValueError:
            return -1

    def setCurrentIndex(self, index: int) -> None:
        self._value = self._options[index]

    def setCurrentText(self, value: str) -> None:
        self._value = value


class _TextInput:
    def __init__(self, value: str):
        self._value = value

    def text(self) -> str:
        return self._value

    def setText(self, value: str) -> None:
        self._value = value


class _Spin:
    def __init__(self, value: float):
        self._value = value

    def value(self) -> float:
        return self._value

    def setValue(self, value: float) -> None:
        self._value = value


class _Check:
    def __init__(self, checked: bool):
        self._checked = checked

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        self._checked = checked


class _ApiControls:
    def __init__(self):
        self.llm_provider_combo = _Combo("OpenRouter")
        self.base_url_edit = _TextInput(" https://llm.example/v1 ")
        self.api_key_edit = _TextInput(" key-123 ")
        self.model_edit = _TextInput(" nous-model ")
        self.temp_spin = _Spin(0.35)
        self.stream_check = _Check(False)
        self.t2i_provider_combo = _Combo("comfyui")
        self.t2i_api_url_edit = _TextInput(" http://127.0.0.1:8188 ")
        self.t2i_checkpoint_edit = _TextInput(" dream.ckpt ")
        self.tts_provider_combo = _Combo("edge")
        self.tts_url_edit = _TextInput(" http://tts.local ")
        self.tts_voice_edit = _TextInput(" zh-CN-XiaoxiaoNeural ")
        self.tts_speed_spin = _Spin(1.25)


class _SkillsTab:
    def collect_default_skills(self) -> list[str]:
        return ["story", "voice"]


class _SystemControls:
    def __init__(self, *, with_checked_skills: bool = True):
        self.lang_combo = _Combo("ja")
        self.voice_lang_combo = _Combo("en")
        self.skills_tab = _SkillsTab() if with_checked_skills else None
        self.system_default_skills_edit = _TextInput(" fallback , custom ,, ")
        self.always_on_top_check = _Check(False)


class _Item:
    def __init__(self, value: str):
        self._value = value

    def text(self) -> str:
        return self._value


class _ListWidget:
    def __init__(self, values: list[str]):
        self._values = values

    def count(self) -> int:
        return len(self._values)

    def item(self, index: int) -> _Item:
        return _Item(self._values[index])

    def addItem(self, value: str) -> None:
        self._values.append(value)


class _BackgroundControls:
    def __init__(self):
        self.scene_list = _ListWidget([" classroom.png ", "park.png"])
        self.background_path_combo = _Combo("", ["", "classroom.png", "park.png"])
        self.bg_tags_edit = _TextInput(" 1-教室 2-公园 ")


class _NamedListWidget(_ListWidget):
    def __init__(self, entries=()):
        super().__init__([])
        self._entries = deepcopy(list(entries))

    def named_entries(self):
        return deepcopy(self._entries)

    def set_named_entries(self, entries):
        self._entries = deepcopy(entries)


class _PlainTextInput:
    def __init__(self, value: str):
        self._value = value

    def toPlainText(self) -> str:
        return self._value


class _CharacterControls:
    char_name_edit = _TextInput(" 露娜 ")
    char_default_skills_edit = _TextInput(" story , voice ,, ")
    char_setting_edit = _PlainTextInput(" 温柔可靠 ")
    emotion_tags_edit = _PlainTextInput("0: legacy-neutral\n1: legacy-happy")
    avatar_path_edit = _TextInput(" imported-avatar.png ")
    refer_audio_path_edit = _TextInput(" reference.wav ")
    prompt_text_edit = _PlainTextInput(" reference text ")
    prompt_lang_combo = _Combo("zh")
    speech_speed_spin = _Spin(1.1)


class _AllSaveControls:
    def __init__(self):
        self.__dict__.update(_ApiControls().__dict__)
        self.__dict__.update(_SystemControls().__dict__)
        self.__dict__.update(_BackgroundControls().__dict__)
        self.char_name_edit = _CharacterControls.char_name_edit
        self.char_default_skills_edit = _CharacterControls.char_default_skills_edit
        self.char_setting_edit = _CharacterControls.char_setting_edit
        self.emotion_tags_edit = _CharacterControls.emotion_tags_edit
        self.avatar_path_edit = _CharacterControls.avatar_path_edit


def _settings_window_method_source(method_name: str) -> str:
    window_path = Path(__file__).resolve().parents[1] / "ui" / "settings_ui" / "window.py"
    source = window_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    settings_class = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SettingsWindow"
    )
    method = next(
        node for node in settings_class.body if isinstance(node, ast.FunctionDef) and node.name == method_name
    )
    return ast.get_source_segment(source, method) or ""


def test_save_service_writes_api_tts_and_t2i_controls_to_api_config():
    module = importlib.import_module("ui.settings_ui.save_service")
    cfg = ApiConfig()

    module.save_api_settings_from_controls(cfg, _ApiControls())

    assert cfg.llm_provider == "OpenRouter"
    assert cfg.llm_base_url == "https://llm.example/v1"
    assert cfg.llm_api_key["OpenRouter"] == "key-123"
    assert cfg.llm_model["OpenRouter"] == "nous-model"
    assert cfg.temperature == 0.35
    assert cfg.is_streaming is False
    assert cfg.t2i_provider == "comfyui"
    assert cfg.t2i_api_url == "http://127.0.0.1:8188"
    assert cfg.t2i_checkpoint == "dream.ckpt"
    assert cfg.tts_provider == "edge"
    assert cfg.gpt_sovits_url == "http://tts.local"
    assert cfg.tts_voice == "zh-CN-XiaoxiaoNeural"
    assert cfg.tts_speed == 1.25


def test_save_service_writes_system_controls_and_prefers_checked_skills():
    module = importlib.import_module("ui.settings_ui.save_service")
    cfg = SystemConfig()

    module.save_system_settings_from_controls(cfg, _SystemControls())

    assert cfg.ui_language == "ja"
    assert cfg.voice_language == "en"
    assert cfg.default_skills == ["story", "voice"]


def test_save_service_falls_back_to_manual_default_skills_when_no_skills_tab():
    module = importlib.import_module("ui.settings_ui.save_service")
    cfg = SystemConfig()

    module.save_system_settings_from_controls(cfg, _SystemControls(with_checked_skills=False))

    assert cfg.default_skills == ["fallback", "custom"]


@pytest.mark.parametrize("payload", [{}, {"always_on_top": None}])
def test_system_config_defaults_main_window_on_top_to_off(payload):
    assert SystemConfig.model_validate(payload).always_on_top is False


@pytest.mark.parametrize("enabled", [False, True])
def test_save_service_preserves_explicit_main_window_on_top_choice(enabled):
    module = importlib.import_module("ui.settings_ui.save_service")
    cfg = SystemConfig(always_on_top=not enabled)
    controls = _SystemControls()
    controls.always_on_top_check.setChecked(enabled)

    module.save_system_settings_from_controls(cfg, controls)

    assert cfg.always_on_top is enabled
    assert SystemConfig.model_validate(cfg.model_dump()).always_on_top is enabled


def test_save_service_writes_background_image_controls_to_app_config():
    module = importlib.import_module("ui.settings_ui.save_service")
    cfg = AppConfig()

    module.save_background_settings_from_controls(cfg, _BackgroundControls())

    assert len(cfg.backgrounds) == 1
    background = cfg.backgrounds[0]
    assert background.name == "背景图库"
    assert [sprite.path for sprite in background.sprites] == [" classroom.png ", "park.png"]
    assert background.bg_tags == "1-教室 2-公园"
    assert background.bgm_list == []
    assert background.bgm_tags == ""


def test_empty_skills_selection_does_not_restore_old_summary():
    from types import SimpleNamespace
    module = importlib.import_module("ui.settings_ui.save_service")
    cfg = SystemConfig(default_skills=["old"])
    controls = _SystemControls()
    controls.skills_tab = SimpleNamespace(collect_default_skills=lambda: [])
    module.save_system_settings_from_controls(cfg, controls)
    assert cfg.default_skills == []


def test_save_service_writes_selected_character_controls_and_archives_sprites():
    module = importlib.import_module("ui.settings_ui.save_service")
    characters = [
        Character(name="保留角色", character_setting="不要改"),
        Character(
            name="旧名",
            default_skills=["old"],
            character_setting="旧设定",
            emotion_tags="legacy-tags",
            sprites=[{"path": "old-sprite.png"}],
        ),
    ]
    collected_emotion_items = [{"id": 2, "label": "happy", "sprite_path": "happy.png"}]
    archive_calls = []

    def _archive(character_name: str, sprites: list) -> list[dict]:
        archive_calls.append((character_name, sprites))
        return [{"path": f"archived/{character_name}.png"}]

    saved = module.save_character_settings_from_controls(
        characters,
        1,
        _CharacterControls(),
        collect_emotion_bindings=lambda: collected_emotion_items,
        archive_character_sprites=_archive,
    )

    assert saved is True
    assert characters[0].name == "保留角色"
    character = characters[1]
    assert character.name == "露娜"
    assert character.default_skills == ["story", "voice"]
    assert character.character_setting == " 温柔可靠 "
    assert character.refer_audio_path == "reference.wav"
    assert character.prompt_text == "reference text"
    assert character.prompt_lang == "zh"
    assert character.speech_speed == 1.1
    assert character.emotion_items == collected_emotion_items
    assert character.emotion_tags == "legacy-tags"
    assert character.sprites == [{"path": "archived/露娜.png"}]
    assert archive_calls[0][0] == "露娜"
    assert [sprite.path for sprite in archive_calls[0][1]] == ["old-sprite.png"]


def test_save_service_writes_and_archives_explicit_avatar():
    module = importlib.import_module("ui.settings_ui.save_service")
    character = Character(name="旧名", avatar="old-avatar.png")
    avatar_calls = []

    def _archive_avatar(character_name: str, avatar_path: str) -> str:
        avatar_calls.append((character_name, avatar_path))
        return f"archived/{character_name}/avatar.png"

    saved = module.save_character_settings_from_controls(
        [character],
        0,
        _CharacterControls(),
        collect_emotion_bindings=lambda: [],
        archive_character_sprites=lambda _name, _sprites: [],
        archive_character_avatar=_archive_avatar,
    )

    assert saved is True
    assert avatar_calls == [("露娜", "imported-avatar.png")]
    assert character.avatar == "archived/露娜/avatar.png"


def test_save_service_writes_legacy_emotion_tags_only_when_no_structured_items_exist():
    module = importlib.import_module("ui.settings_ui.save_service")
    character = Character(name="旧名", emotion_tags="", sprites=[])

    saved = module.save_character_settings_from_controls(
        [character],
        0,
        _CharacterControls(),
        collect_emotion_bindings=lambda: [],
        archive_character_sprites=lambda _name, _sprites: [],
    )

    assert saved is True
    assert character.emotion_tags == "0: legacy-neutral\n1: legacy-happy"


def test_save_service_ignores_invalid_character_index_without_touching_controls():
    module = importlib.import_module("ui.settings_ui.save_service")
    character = Character(name="旧名", character_setting="不应修改")

    saved = module.save_character_settings_from_controls(
        [character],
        9,
        _CharacterControls(),
        collect_emotion_bindings=lambda: (_ for _ in ()).throw(AssertionError("should not collect")),
        archive_character_sprites=lambda _name, _sprites: (_ for _ in ()).throw(AssertionError("should not archive")),
    )

    assert saved is False
    assert character.name == "旧名"
    assert character.character_setting == "不应修改"


def test_save_service_loads_api_system_and_background_config_into_controls():
    module = importlib.import_module("ui.settings_ui.save_service")
    config = AppConfig(
        api_config=ApiConfig(
            llm_provider="aipaibox",
            llm_api_key={"aipaibox": "sk-local"},
            llm_base_url="https://llm.example/v1",
            llm_model={"aipaibox": "claude-opus-4-7"},
            temperature=0.42,
            is_streaming=False,
            t2i_provider="comfyui",
            t2i_api_url="http://127.0.0.1:8188",
            t2i_checkpoint="animagine.safetensors",
            tts_provider="edge",
            gpt_sovits_url="http://tts.local",
            tts_voice="zh-CN-XiaoxiaoNeural",
            tts_speed=1.15,
        ),
        system_config=SystemConfig(
            ui_language="ja",
            voice_language="en",
            default_skills=["story", "voice"],
            always_on_top=True,
        ),
        backgrounds=[
            {
                "name": "默认场景组",
                "sprites": [{"path": "classroom.png"}, {"path": "park.png"}],
                "bg_tags": "1-教室 2-公园",
                "bgm_list": ["daily.ogg", " tension.ogg "],
                "bgm_tags": "1-日常 2-紧张",
            }
        ],
    )
    controls = _AllSaveControls()
    controls.llm_provider_combo = _Combo("deepseek", ["deepseek", "custom"])
    controls.t2i_provider_combo = _Combo("none", ["none", "comfyui"])
    controls.tts_provider_combo = _Combo("none", ["none", "edge"])
    controls.lang_combo = _Combo("zh_CN", ["zh_CN", "ja"])
    controls.voice_lang_combo = _Combo("ja", ["ja", "en"])
    controls.scene_list = _ListWidget([])

    module.load_settings_into_controls(config, controls)

    assert controls.llm_provider_combo.currentText() == "custom"
    assert controls.api_key_edit.text() == "sk-local"
    assert controls.base_url_edit.text() == "https://llm.example/v1"
    assert controls.model_edit.text() == "claude-opus-4-7"
    assert controls.temp_spin.value() == 0.42
    assert controls.stream_check.isChecked() is False
    assert controls.t2i_provider_combo.currentText() == "comfyui"
    assert controls.t2i_api_url_edit.text() == "http://127.0.0.1:8188"
    assert controls.t2i_checkpoint_edit.text() == "animagine.safetensors"
    assert controls.tts_provider_combo.currentText() == "edge"
    assert controls.tts_url_edit.text() == "http://tts.local"
    assert controls.tts_voice_edit.text() == "zh-CN-XiaoxiaoNeural"
    assert controls.tts_speed_spin.value() == 1.15
    assert controls.lang_combo.currentText() == "ja"
    assert controls.voice_lang_combo.currentText() == "en"
    assert controls.system_default_skills_edit.text() == "story, voice"
    assert controls.always_on_top_check.isChecked() is True
    assert [controls.scene_list.item(i).text() for i in range(controls.scene_list.count())] == ["classroom.png", "park.png"]
    assert controls.bg_tags_edit.text() == "1-教室 2-公园"


def test_settings_window_load_config_delegates_config_mapping_to_save_service():
    method_source = _settings_window_method_source("_load_config")

    assert "load_settings_into_controls(" in method_source
    assert "cfg = self.config.api_config" not in method_source
    assert "self.api_key_edit.setText" not in method_source
    assert "self.base_url_edit.setText" not in method_source
    assert "self.model_edit.setText" not in method_source
    assert "self.t2i_api_url_edit.setText" not in method_source
    assert "self.tts_url_edit.setText" not in method_source
    assert "self.system_default_skills_edit.setText" not in method_source
    assert "self.scene_list.addItem" not in method_source
    assert "self.bgm_list.addItem" not in method_source
    assert "self.bg_tags_edit.setText" not in method_source
    assert "self.bgm_tags_edit.setText" not in method_source


def test_save_service_orchestrates_all_settings_mapping_and_persistence_calls():
    module = importlib.import_module("ui.settings_ui.save_service")

    class _ConfigStore:
        def __init__(self):
            self.api_config = ApiConfig()
            self.system_config = SystemConfig()
            self.characters = [Character(name="旧名", character_setting="旧设定", sprites=[{"path": "old.png"}])]
            self.config = AppConfig(characters=self.characters)
            self.saved_calls = []

        def save_api_config(self):
            self.saved_calls.append("api")

        def save_characters(self):
            self.saved_calls.append("characters")

        def save_system_config(self):
            self.saved_calls.append("system")

        def save_mcp_servers(self):
            self.saved_calls.append("mcp")

        def save_backgrounds(self):
            self.saved_calls.append("backgrounds")

    store = _ConfigStore()
    archive_calls = []

    def _archive(character_name: str, sprites: list) -> list[dict]:
        archive_calls.append((character_name, sprites))
        return [{"path": f"archived/{character_name}.png"}]

    character_saved = module.save_settings_from_controls(
        store,
        _AllSaveControls(),
        current_character_index=0,
        collect_emotion_bindings=lambda: [],
        archive_character_sprites=_archive,
    )

    assert character_saved is True
    assert store.api_config.t2i_checkpoint == "dream.ckpt"
    assert store.system_config.default_skills == ["story", "voice"]
    assert store.characters[0].name == "露娜"
    assert store.config.backgrounds[0].bg_tags == "1-教室 2-公园"
    assert store.saved_calls == ["api", "characters", "system", "mcp", "backgrounds"]
    assert archive_calls[0][0] == "露娜"


def test_save_service_maps_all_controls_before_starting_persistence():
    module = importlib.import_module("ui.settings_ui.save_service")

    class _ConfigStore:
        def __init__(self):
            self.api_config = ApiConfig()
            self.system_config = SystemConfig()
            self.characters = [Character(name="旧名", sprites=[{"path": "old.png"}])]
            self.config = AppConfig(characters=self.characters)
            self.saved_calls = []

        def save_api_config(self):
            self.saved_calls.append("api")

        def save_characters(self):
            self.saved_calls.append("characters")

        def save_system_config(self):
            self.saved_calls.append("system")

        def save_mcp_servers(self):
            self.saved_calls.append("mcp")

        def save_backgrounds(self):
            self.saved_calls.append("backgrounds")

    store = _ConfigStore()

    before_api = store.api_config.model_copy(deep=True)
    before_system = store.system_config.model_copy(deep=True)
    before_characters = deepcopy(store.characters)
    before_backgrounds = deepcopy(store.config.backgrounds)

    def _archive_that_fails(_character_name: str, _sprites: list) -> list[dict]:
        raise OSError("archive failed")

    with pytest.raises(OSError, match="archive failed"):
        module.save_settings_from_controls(
            store,
            _AllSaveControls(),
            current_character_index=0,
            collect_emotion_bindings=lambda: [],
            archive_character_sprites=_archive_that_fails,
        )

    assert store.saved_calls == []
    assert store.api_config == before_api
    assert store.system_config == before_system
    assert store.characters == before_characters
    assert store.config.backgrounds == before_backgrounds


def test_save_service_rolls_back_memory_when_persistence_fails():
    module = importlib.import_module("ui.settings_ui.save_service")

    for failing_step in ["api", "characters", "system", "mcp", "backgrounds"]:
        class _ConfigStore:
            def __init__(self):
                self.api_config = ApiConfig()
                self.system_config = SystemConfig()
                self.characters = [Character(name="旧名", sprites=[{"path": "old.png"}])]
                self.config = AppConfig(
                    api_config=self.api_config,
                    system_config=self.system_config,
                    characters=self.characters,
                )
                self.saved_calls = []

            def _save(self, name):
                self.saved_calls.append(name)
                if name == failing_step:
                    raise OSError(f"{name} failed")

            def save_api_config(self): self._save("api")
            def save_characters(self): self._save("characters")
            def save_system_config(self): self._save("system")
            def save_mcp_servers(self): self._save("mcp")
            def save_backgrounds(self): self._save("backgrounds")

        store = _ConfigStore()
        before = store.config.model_copy(deep=True)

        with pytest.raises(OSError, match=f"{failing_step} failed"):
            module.save_settings_from_controls(
                store,
                _AllSaveControls(),
                current_character_index=0,
                collect_emotion_bindings=lambda: [],
                archive_character_sprites=lambda name, sprites: [{"path": f"archived/{name}.png"}],
            )

        assert store.config == before
        assert store.api_config == before.api_config
        assert store.system_config == before.system_config
        assert store.characters == before.characters


def test_config_manager_persistence_transaction_restores_files_on_failure(tmp_path, monkeypatch):
    module = importlib.import_module("config.config_manager")
    manager_class = module.ConfigManager
    paths = {
        "_API_LOCAL_CONFIG_PATH": tmp_path / "api.local.yaml",
        "_CHARACTERS_CONFIG_PATH": tmp_path / "characters.yaml",
        "_SYSTEM_CONFIG_PATH": tmp_path / "system.yaml",
        "_BACKGROUND_CONFIG_PATH": tmp_path / "background.yaml",
        "_MCP_CONFIG_PATH": tmp_path / "mcp.yaml",
    }
    for attribute, path in paths.items():
        monkeypatch.setattr(manager_class, attribute, path)
        path.write_text(f"original-{attribute}", encoding="utf-8")

    manager_class.reset()
    manager = manager_class()
    before = {path: path.read_bytes() for path in paths.values()}

    with pytest.raises(OSError, match="persistence failed"):
        with manager.persistence_transaction():
            for path in paths.values():
                path.write_text("changed", encoding="utf-8")
            raise OSError("persistence failed")

    assert {path: path.read_bytes() for path in paths.values()} == before


def test_config_manager_persistence_transaction_removes_new_files_on_failure(tmp_path, monkeypatch):
    module = importlib.import_module("config.config_manager")
    manager_class = module.ConfigManager
    existing = tmp_path / "api.local.yaml"
    existing.write_text("original-api", encoding="utf-8")
    paths = {
        "_API_LOCAL_CONFIG_PATH": existing,
        "_CHARACTERS_CONFIG_PATH": tmp_path / "characters.yaml",
        "_SYSTEM_CONFIG_PATH": tmp_path / "system.yaml",
        "_BACKGROUND_CONFIG_PATH": tmp_path / "background.yaml",
        "_MCP_CONFIG_PATH": tmp_path / "mcp.yaml",
    }
    for attribute, path in paths.items():
        monkeypatch.setattr(manager_class, attribute, path)

    manager_class.reset()
    manager = manager_class()

    with pytest.raises(OSError, match="persistence failed"):
        with manager.persistence_transaction():
            for path in paths.values():
                path.write_text("changed", encoding="utf-8")
            raise OSError("persistence failed")

    assert existing.read_text(encoding="utf-8") == "original-api"
    assert all(not path.exists() for path in list(paths.values())[1:])


def test_config_manager_persistence_transaction_restores_sprite_files(tmp_path, monkeypatch):
    module = importlib.import_module("config.config_manager")
    manager_class = module.ConfigManager
    config_root = tmp_path / "data" / "config"
    sprite_root = tmp_path / "data" / "sprites" / "hero"
    config_root.mkdir(parents=True)
    sprite_root.mkdir(parents=True)
    existing_sprite = sprite_root / "portrait.png"
    existing_sprite.write_bytes(b"original")
    monkeypatch.setattr(manager_class, "_CHARACTERS_CONFIG_PATH", config_root / "characters.yaml")

    manager_class.reset()
    manager = manager_class()

    with pytest.raises(OSError, match="save failed"):
        with manager.persistence_transaction():
            existing_sprite.write_bytes(b"overwritten")
            (sprite_root / "new.png").write_bytes(b"new")
            raise OSError("save failed")

    assert existing_sprite.read_bytes() == b"original"
    assert not (sprite_root / "new.png").exists()


def test_config_manager_persistence_transaction_restores_avatar_files(tmp_path, monkeypatch):
    module = importlib.import_module("config.config_manager")
    manager_class = module.ConfigManager
    config_root = tmp_path / "data" / "config"
    avatar_root = tmp_path / "data" / "avatars" / "hero"
    config_root.mkdir(parents=True)
    avatar_root.mkdir(parents=True)
    existing_avatar = avatar_root / "portrait.png"
    existing_avatar.write_bytes(b"original")
    monkeypatch.setattr(manager_class, "_CHARACTERS_CONFIG_PATH", config_root / "characters.yaml")

    manager_class.reset()
    manager = manager_class()

    with pytest.raises(OSError, match="save failed"):
        with manager.persistence_transaction():
            existing_avatar.write_bytes(b"overwritten")
            (avatar_root / "new.png").write_bytes(b"new")
            raise OSError("save failed")

    assert existing_avatar.read_bytes() == b"original"
    assert not (avatar_root / "new.png").exists()


def test_settings_window_save_config_delegates_save_orchestration_to_save_service():
    method_source = _settings_window_method_source("_save_config")

    assert "save_settings_from_controls(" in method_source
    assert "save_api_settings_from_controls(cfg, self)" not in method_source
    assert "save_system_settings_from_controls(sys_cfg, self)" not in method_source
    assert "save_character_settings_from_controls(" not in method_source
    assert "save_background_settings_from_controls(self.config.config, self)" not in method_source
    assert "self.config.save_api_config()" not in method_source
    assert "self.config.save_characters()" not in method_source
    assert "self.config.save_system_config()" not in method_source
    assert "self.config.save_mcp_servers()" not in method_source
    assert "self.config.save_backgrounds()" not in method_source
    assert "cfg.llm_provider =" not in method_source
    assert "cfg.t2i_provider =" not in method_source
    assert "cfg.tts_provider =" not in method_source
    assert "sys_cfg.ui_language =" not in method_source
    assert "sys_cfg.voice_language =" not in method_source
    assert "sys_cfg.default_skills =" not in method_source
    assert "char = self.config.characters" not in method_source
    assert "char.default_skills =" not in method_source
    assert "char.character_setting =" not in method_source
    assert "char.emotion_items =" not in method_source
    assert "char.emotion_tags =" not in method_source
    assert "char.sprites =" not in method_source
    assert "Background(" not in method_source
    assert "self.config.config.backgrounds =" not in method_source


def test_save_service_named_backgrounds_preserve_inert_legacy_music_values():
    module = importlib.import_module("ui.settings_ui.save_service")
    controls = _BackgroundControls()
    scenes = [
        {"path": "park.png", "label": "夜晚 公园"},
        {"path": "room.png", "label": "中文 教室 🌿"},
    ]
    controls.scene_list = _NamedListWidget(scenes)
    cfg = AppConfig(backgrounds=[Background(name="旧配置", bgm_list=["old.ogg"], bgm_tags="1:旧音乐")])

    module.save_background_settings_from_controls(cfg, controls)
    background = cfg.backgrounds[0]

    assert [binding.model_dump() for binding in background.scene_bindings] == scenes
    assert [sprite.path for sprite in background.sprites] == ["park.png", "room.png"]
    assert background.bg_tags == "1: 夜晚 公园\n2: 中文 教室 🌿"
    assert background.bgm_list == ["old.ogg"]
    assert background.bgm_tags == "1:旧音乐"
    assert not hasattr(controls, "bgm_list")


def test_save_service_named_backgrounds_fallback_empty_names():
    module = importlib.import_module("ui.settings_ui.save_service")
    controls = _BackgroundControls()
    controls.scene_list = _NamedListWidget([{"path": "清晨 校园.png", "label": " "}])
    del controls.bg_tags_edit
    cfg = AppConfig()

    module.save_background_settings_from_controls(cfg, controls)

    background = cfg.backgrounds[0]
    assert background.scene_bindings[0].label == "清晨 校园"
    assert background.bg_tags == "1: 清晨 校园"


def test_save_service_loads_legacy_background_names_and_manual_no_background_choice():
    module = importlib.import_module("ui.settings_ui.save_service")
    controls = _AllSaveControls()
    controls.scene_list = _NamedListWidget()
    cfg = AppConfig(backgrounds=[Background(
        name="旧配置", sprites=[{"path": "room.png"}, {"path": "park.png"}],
        bg_tags="1-教室 2-夜晚 公园", bgm_list=["calm.ogg"], bgm_tags="1:平静 日常",
    )])

    module.load_settings_into_controls(cfg, controls)

    assert controls.scene_list.named_entries() == [
        {"path": "room.png", "label": "教室"}, {"path": "park.png", "label": "夜晚 公园"},
    ]
    assert controls.background_path_combo.currentData() == ""
    assert not hasattr(controls, "bgm_list")


def test_save_service_roundtrip_delete_reorder_keeps_bound_names():
    module = importlib.import_module("ui.settings_ui.save_service")
    cfg = AppConfig()
    controls = _AllSaveControls()
    controls.scene_list = _NamedListWidget([
        {"path": "room.png", "label": "教室"},
        {"path": "removed.png", "label": "待删除"},
        {"path": "park.png", "label": "夜晚 公园"},
    ])
    module.save_background_settings_from_controls(cfg, controls)

    cfg.backgrounds[0].sprites = [cfg.backgrounds[0].sprites[2], cfg.backgrounds[0].sprites[0]]
    module.load_settings_into_controls(cfg, controls)
    module.save_background_settings_from_controls(cfg, controls)

    background = cfg.backgrounds[0]
    assert [item.model_dump() for item in background.scene_bindings] == [
        {"path": "park.png", "label": "夜晚 公园"}, {"path": "room.png", "label": "教室"},
    ]


def test_save_service_empty_configuration_clears_existing_named_backgrounds():
    module = importlib.import_module("ui.settings_ui.save_service")
    controls = _AllSaveControls()
    controls.scene_list = _NamedListWidget([{"path": "old.png", "label": "旧场景"}])

    module.load_settings_into_controls(AppConfig(), controls)

    assert controls.scene_list.named_entries() == []
    assert controls.background_path_combo.currentData() == ""


def test_save_system_preserves_manual_path_and_explicit_no_background():
    module = importlib.import_module("ui.settings_ui.save_service")
    controls = _AllSaveControls()
    controls.background_path_combo.setCurrentText("park.png")
    cfg = SystemConfig(background_path="old.png")
    module.save_system_settings_from_controls(cfg, controls)
    assert cfg.background_path == "park.png"
    controls.background_path_combo.setCurrentText("")
    module.save_system_settings_from_controls(cfg, controls)
    assert cfg.background_path == ""
