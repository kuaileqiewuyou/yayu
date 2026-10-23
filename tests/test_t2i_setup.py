from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from config.config_manager import ConfigManager
from config.schema import ApiConfig, AppConfig
from core.runtime.t2i_setup import create_t2i_manager
from t2i.t2i_manager import ComfyUIAdapter, T2IAdapterFactory


@pytest.fixture(autouse=True)
def reset_config_manager():
    ConfigManager.reset()
    yield
    ConfigManager.reset()


@dataclass
class FakeApiConfig:
    t2i_provider: str = "none"
    t2i_api_url: str = "http://t2i.local"
    t2i_checkpoint: str = "v1-5-pruned-emaonly.ckpt"


@dataclass
class FakeConfig:
    api_config: FakeApiConfig

class FakeAdapter:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def generate(self, prompt: str, **kwargs):
        return None

class StrictAdapter:
    def __init__(self, api_url: str):
        self.api_url = api_url

    def generate(self, prompt: str, **kwargs):
        return None


def make_config(provider="none", api_url="http://t2i.local", checkpoint="v1-5-pruned-emaonly.ckpt"):
    return FakeConfig(api_config=FakeApiConfig(
        t2i_provider=provider,
        t2i_api_url=api_url,
        t2i_checkpoint=checkpoint,
    ))


def test_config_manager_loads_api_local_yaml_over_base_api_yaml(tmp_path, monkeypatch):
    api_path = tmp_path / "api.yaml"
    api_local_path = tmp_path / "api.local.yaml"
    system_path = tmp_path / "system_config.yaml"
    characters_path = tmp_path / "characters.yaml"
    background_path = tmp_path / "background.yaml"

    api_path.write_text(
        yaml.safe_dump(
            {
                "t2i_provider": "none",
                "t2i_api_url": "http://127.0.0.1:8188",
                "t2i_checkpoint": "v1-5-pruned-emaonly.ckpt",
                "tts_provider": "none",
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    api_local_path.write_text(
        yaml.safe_dump(
            {
                "t2i_provider": "comfyui",
                "t2i_api_url": "http://127.0.0.1:8000",
                "t2i_checkpoint": "noobaiXLNAIXL_epsilonPred11Version.safetensors",
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    system_path.write_text("{}\n", encoding="utf-8")
    characters_path.write_text("[]\n", encoding="utf-8")
    background_path.write_text("[]\n", encoding="utf-8")

    monkeypatch.setattr(ConfigManager, "_API_CONFIG_PATH", api_path)
    monkeypatch.setattr(ConfigManager, "_API_LOCAL_CONFIG_PATH", api_local_path)
    monkeypatch.setattr(ConfigManager, "_SYSTEM_CONFIG_PATH", system_path)
    monkeypatch.setattr(ConfigManager, "_CHARACTERS_CONFIG_PATH", characters_path)
    monkeypatch.setattr(ConfigManager, "_BACKGROUND_CONFIG_PATH", background_path)
    ConfigManager.reset()

    config = ConfigManager().api_config

    assert config.t2i_provider == "comfyui"
    assert config.t2i_api_url == "http://127.0.0.1:8000"
    assert config.t2i_checkpoint == "noobaiXLNAIXL_epsilonPred11Version.safetensors"
    assert config.tts_provider == "none"


def test_config_manager_deep_merges_local_provider_dicts_over_base(tmp_path, monkeypatch):
    api_path = tmp_path / "api.yaml"
    api_local_path = tmp_path / "api.local.yaml"
    system_path = tmp_path / "system_config.yaml"
    characters_path = tmp_path / "characters.yaml"
    background_path = tmp_path / "background.yaml"

    api_path.write_text(
        yaml.safe_dump(
            {
                "llm_provider": "openai",
                "llm_api_key": {"openai": "base-openai-key", "deepseek": "base-deepseek-key"},
                "llm_model": {"openai": "gpt-4o-mini", "deepseek": "deepseek-chat"},
                "t2i_provider": "none",
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    api_local_path.write_text(
        yaml.safe_dump(
            {
                "llm_api_key": {"openai": "local-openai-key"},
                "llm_model": {"openai": "local-openai-model"},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    system_path.write_text("{}\n", encoding="utf-8")
    characters_path.write_text("[]\n", encoding="utf-8")
    background_path.write_text("[]\n", encoding="utf-8")

    monkeypatch.setattr(ConfigManager, "_API_CONFIG_PATH", api_path)
    monkeypatch.setattr(ConfigManager, "_API_LOCAL_CONFIG_PATH", api_local_path)
    monkeypatch.setattr(ConfigManager, "_SYSTEM_CONFIG_PATH", system_path)
    monkeypatch.setattr(ConfigManager, "_CHARACTERS_CONFIG_PATH", characters_path)
    monkeypatch.setattr(ConfigManager, "_BACKGROUND_CONFIG_PATH", background_path)

    config = ConfigManager().api_config

    assert config.llm_api_key["openai"] == "local-openai-key"
    assert config.llm_api_key["deepseek"] == "base-deepseek-key"
    assert config.llm_model["openai"] == "local-openai-model"
    assert config.llm_model["deepseek"] == "deepseek-chat"


def test_config_manager_saves_api_config_to_existing_local_overlay(tmp_path, monkeypatch):
    api_path = tmp_path / "api.yaml"
    api_local_path = tmp_path / "api.local.yaml"
    system_path = tmp_path / "system_config.yaml"
    characters_path = tmp_path / "characters.yaml"
    background_path = tmp_path / "background.yaml"

    api_path.write_text(yaml.safe_dump({"t2i_provider": "none"}), encoding="utf-8")
    api_local_path.write_text(yaml.safe_dump({"t2i_provider": "comfyui"}), encoding="utf-8")
    system_path.write_text("{}\n", encoding="utf-8")
    characters_path.write_text("[]\n", encoding="utf-8")
    background_path.write_text("[]\n", encoding="utf-8")

    monkeypatch.setattr(ConfigManager, "_API_CONFIG_PATH", api_path)
    monkeypatch.setattr(ConfigManager, "_API_LOCAL_CONFIG_PATH", api_local_path)
    monkeypatch.setattr(ConfigManager, "_SYSTEM_CONFIG_PATH", system_path)
    monkeypatch.setattr(ConfigManager, "_CHARACTERS_CONFIG_PATH", characters_path)
    monkeypatch.setattr(ConfigManager, "_BACKGROUND_CONFIG_PATH", background_path)
    ConfigManager.reset()

    manager = ConfigManager()
    manager.config.api_config.t2i_api_url = "http://127.0.0.1:8000"
    manager.save_api_config()

    base_raw = yaml.safe_load(api_path.read_text(encoding="utf-8"))
    local_raw = yaml.safe_load(api_local_path.read_text(encoding="utf-8"))

    assert base_raw == {"t2i_provider": "none"}
    assert local_raw["t2i_provider"] == "comfyui"
    assert local_raw["t2i_api_url"] == "http://127.0.0.1:8000"
    ConfigManager.reset()


def test_config_manager_saves_api_config_to_new_local_overlay_when_no_local_exists(tmp_path, monkeypatch):
    api_path = tmp_path / "api.yaml"
    api_local_path = tmp_path / "api.local.yaml"
    system_path = tmp_path / "system_config.yaml"
    characters_path = tmp_path / "characters.yaml"
    background_path = tmp_path / "background.yaml"

    api_path.write_text(yaml.safe_dump({"t2i_provider": "none"}), encoding="utf-8")
    system_path.write_text("{}\n", encoding="utf-8")
    characters_path.write_text("[]\n", encoding="utf-8")
    background_path.write_text("[]\n", encoding="utf-8")

    monkeypatch.setattr(ConfigManager, "_API_CONFIG_PATH", api_path)
    monkeypatch.setattr(ConfigManager, "_API_LOCAL_CONFIG_PATH", api_local_path)
    monkeypatch.setattr(ConfigManager, "_SYSTEM_CONFIG_PATH", system_path)
    monkeypatch.setattr(ConfigManager, "_CHARACTERS_CONFIG_PATH", characters_path)
    monkeypatch.setattr(ConfigManager, "_BACKGROUND_CONFIG_PATH", background_path)

    manager = ConfigManager()
    manager.config.api_config.t2i_provider = "comfyui"
    manager.save_api_config()

    base_raw = yaml.safe_load(api_path.read_text(encoding="utf-8"))
    local_raw = yaml.safe_load(api_local_path.read_text(encoding="utf-8"))
    assert base_raw == {"t2i_provider": "none"}
    assert local_raw["t2i_provider"] == "comfyui"


def test_sample_api_yaml_keeps_t2i_disabled_by_default():
    config_path = Path("data/config/api.yaml")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert raw["t2i_provider"] == "none"
    assert raw["t2i_api_url"] == "http://127.0.0.1:8188"


def test_sample_api_yaml_contains_no_private_api_keys():
    config_path = Path("data/config/api.yaml")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert raw.get("llm_api_key") == {}
    assert "sk-" not in config_path.read_text(encoding="utf-8")


def test_sample_api_yaml_uses_no_network_llm_by_default():
    config_path = Path("data/config/api.yaml")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert raw["llm_base_url"] == ""
    assert raw["llm_model"] == {}
    assert raw["llm_provider"] == "OpenAI"
    assert raw["tts_provider"] == "none"


def test_sample_api_yaml_documents_default_comfyui_checkpoint():
    config_path = Path("data/config/api.yaml")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert raw["t2i_checkpoint"] == "v1-5-pruned-emaonly.ckpt"


def test_api_config_documents_default_comfyui_url():
    config = ApiConfig()

    assert config.t2i_provider == "none"
    assert config.t2i_api_url == "http://127.0.0.1:8188"


def test_api_config_documents_default_comfyui_checkpoint():
    config = ApiConfig()

    assert config.t2i_checkpoint == "v1-5-pruned-emaonly.ckpt"


def test_create_t2i_manager_returns_none_when_provider_is_none():
    manager = create_t2i_manager(make_config(provider="none"))

    assert manager is None


def test_create_t2i_manager_returns_none_when_provider_is_empty():
    manager = create_t2i_manager(make_config(provider=""))

    assert manager is None


def test_create_t2i_manager_returns_none_for_real_default_api_config():
    assert ApiConfig().t2i_provider == "none"

    manager = create_t2i_manager(AppConfig())

    assert manager is None


def test_create_t2i_manager_normalizes_provider_before_disable_or_create(monkeypatch):
    created = []

    def fake_create_adapter(name, **kwargs):
        created.append({"name": name, "kwargs": kwargs})
        return FakeAdapter(**kwargs)

    monkeypatch.setattr(T2IAdapterFactory, "create_adapter", fake_create_adapter)

    assert create_t2i_manager(make_config(provider=" None ")) is None

    manager = create_t2i_manager(make_config(provider=" ComfyUI ", api_url="http://comfy"))

    assert created == [
        {
            "name": "comfyui",
            "kwargs": {
                "api_url": "http://comfy",
                "checkpoint": "v1-5-pruned-emaonly.ckpt",
                "poll_attempts": ComfyUIAdapter.DEFAULT_POLL_ATTEMPTS,
                "poll_interval": ComfyUIAdapter.DEFAULT_POLL_INTERVAL,
            },
        }
    ]
    assert isinstance(manager.adapter, FakeAdapter)


def test_create_t2i_manager_uses_production_comfyui_polling_defaults(monkeypatch):
    created = []

    def fake_create_adapter(name, **kwargs):
        created.append({"name": name, "kwargs": kwargs})
        return FakeAdapter(**kwargs)

    monkeypatch.setattr(T2IAdapterFactory, "create_adapter", fake_create_adapter)

    manager = create_t2i_manager(make_config(provider="comfyui", api_url="http://comfy"))

    assert isinstance(manager.adapter, FakeAdapter)
    assert created[0]["name"] == "comfyui"
    assert created[0]["kwargs"]["api_url"] == "http://comfy"
    assert created[0]["kwargs"]["checkpoint"] == "v1-5-pruned-emaonly.ckpt"
    assert created[0]["kwargs"]["poll_attempts"] == ComfyUIAdapter.DEFAULT_POLL_ATTEMPTS
    assert created[0]["kwargs"]["poll_interval"] == ComfyUIAdapter.DEFAULT_POLL_INTERVAL


def test_create_t2i_manager_passes_custom_comfyui_checkpoint(monkeypatch):
    created = []

    def fake_create_adapter(name, **kwargs):
        created.append({"name": name, "kwargs": kwargs})
        return FakeAdapter(**kwargs)

    monkeypatch.setattr(T2IAdapterFactory, "create_adapter", fake_create_adapter)

    manager = create_t2i_manager(
        make_config(provider="comfyui", api_url="http://comfy", checkpoint="local-model.safetensors")
    )

    assert isinstance(manager.adapter, FakeAdapter)
    assert created[0]["kwargs"]["checkpoint"] == "local-model.safetensors"


def test_create_t2i_manager_does_not_pass_comfyui_polling_kwargs_to_other_providers(monkeypatch):
    adapters = dict(T2IAdapterFactory._adapters)
    adapters["strict"] = StrictAdapter
    monkeypatch.setattr(T2IAdapterFactory, "_adapters", adapters)

    manager = create_t2i_manager(make_config(provider="strict", api_url="http://strict"))

    assert isinstance(manager.adapter, StrictAdapter)
    assert manager.adapter.api_url == "http://strict"


def test_create_t2i_manager_returns_none_when_api_config_is_missing():
    manager = create_t2i_manager(object())

    assert manager is None


def test_create_t2i_manager_initializes_adapter(monkeypatch, capsys):
    created = []
    def fake_create_adapter(name, **kwargs):
        created.append({"name": name, "kwargs": kwargs})
        return FakeAdapter(**kwargs)

    monkeypatch.setattr(T2IAdapterFactory, "create_adapter", fake_create_adapter)

    manager = create_t2i_manager(make_config(provider="comfyui", api_url="http://comfy"))

    assert created == [
        {
            "name": "comfyui",
            "kwargs": {
                "api_url": "http://comfy",
                "checkpoint": "v1-5-pruned-emaonly.ckpt",
                "poll_attempts": ComfyUIAdapter.DEFAULT_POLL_ATTEMPTS,
                "poll_interval": ComfyUIAdapter.DEFAULT_POLL_INTERVAL,
            },
        }
    ]
    assert isinstance(manager.adapter, FakeAdapter)
    assert manager.adapter.kwargs == {
        "api_url": "http://comfy",
        "checkpoint": "v1-5-pruned-emaonly.ckpt",
        "poll_attempts": ComfyUIAdapter.DEFAULT_POLL_ATTEMPTS,
        "poll_interval": ComfyUIAdapter.DEFAULT_POLL_INTERVAL,
    }
    assert "[T2I] 已启用: comfyui" in capsys.readouterr().out


def test_create_t2i_manager_keeps_t2i_disabled_when_adapter_initialization_fails(monkeypatch, capsys):
    def fake_create_adapter(name, **kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(T2IAdapterFactory, "create_adapter", fake_create_adapter)

    manager = create_t2i_manager(make_config(provider="bad-provider"))

    assert manager is None
    assert "[T2I] 初始化失败: boom，图像生成功能已禁用" in capsys.readouterr().out
