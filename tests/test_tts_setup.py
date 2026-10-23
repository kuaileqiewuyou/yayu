from dataclasses import dataclass

import pytest

from config.schema import DEFAULT_TTS_VOICE, ApiConfig
from core.runtime.tts_setup import create_tts_manager
from tts.tts_adapter import TTSAdapterFactory


def test_api_config_has_default_tts_voice():
    config = ApiConfig()

    assert config.tts_voice == DEFAULT_TTS_VOICE


@dataclass
class FakeApiConfig:
    gpt_sovits_url: str = "http://tts.local"
    tts_provider: str = "none"
    tts_speed: float = 1.0
    tts_voice: str = DEFAULT_TTS_VOICE


@dataclass
class FakeSystemConfig:
    voice_language: str = "ja"


@dataclass
class FakeConfig:
    api_config: FakeApiConfig
    system_config: FakeSystemConfig


class FakeAdapter:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def synthesize(self, text: str, speaker: str = "", language: str = "ja", speed: float = 1.0):
        return None


def make_config(provider="none", url="http://tts.local", language="ja", speed=1.0, voice=DEFAULT_TTS_VOICE):
    return FakeConfig(
        api_config=FakeApiConfig(gpt_sovits_url=url, tts_provider=provider, tts_speed=speed, tts_voice=voice),
        system_config=FakeSystemConfig(voice_language=language),
    )


def test_create_tts_manager_returns_disabled_manager_when_provider_is_none():
    manager = create_tts_manager(make_config(provider="none"))

    assert manager.tts_server_url == "http://tts.local"
    assert manager.adapter is None
    assert manager.language == "ja"
    assert manager.speed == 1.0


def test_create_tts_manager_returns_disabled_manager_when_provider_is_empty():
    manager = create_tts_manager(make_config(provider=""))

    assert manager.tts_server_url == "http://tts.local"
    assert manager.adapter is None


def test_create_tts_manager_initializes_gpt_sovits_adapter(monkeypatch, capsys):
    created = []

    def fake_create_adapter(name, **kwargs):
        created.append({"name": name, "kwargs": kwargs})
        return FakeAdapter(**kwargs)

    monkeypatch.setattr(TTSAdapterFactory, "create_adapter", fake_create_adapter)

    manager = create_tts_manager(
        make_config(provider="gpt-sovits", url="http://gpt-sovits", language="zh", speed=1.25)
    )

    assert created == [{"name": "gpt-sovits", "kwargs": {"server_url": "http://gpt-sovits"}}]
    assert isinstance(manager.adapter, FakeAdapter)
    assert manager.adapter.kwargs == {"server_url": "http://gpt-sovits"}
    assert manager.language == "zh"
    assert manager.speed == 1.25
    assert "[TTS] 已启用: gpt-sovits" in capsys.readouterr().out


def test_create_tts_manager_initializes_edge_tts_adapter_with_configured_voice(monkeypatch):
    created = []

    def fake_create_adapter(name, **kwargs):
        created.append({"name": name, "kwargs": kwargs})
        return FakeAdapter(**kwargs)

    monkeypatch.setattr(TTSAdapterFactory, "create_adapter", fake_create_adapter)

    manager = create_tts_manager(
        make_config(provider="edge-tts", language="en", speed=0.9, voice="ja-JP-NanamiNeural")
    )

    assert created == [{"name": "edge-tts", "kwargs": {"voice": "ja-JP-NanamiNeural"}}]
    assert isinstance(manager.adapter, FakeAdapter)
    assert manager.adapter.kwargs == {"voice": "ja-JP-NanamiNeural"}
    assert manager.language == "en"
    assert manager.speed == 0.9


@pytest.mark.parametrize("blank_voice", ["", "   \t\n"])
def test_create_tts_manager_initializes_edge_tts_adapter_with_default_voice_when_voice_is_blank(
    monkeypatch, blank_voice
):
    created = []

    def fake_create_adapter(name, **kwargs):
        created.append({"name": name, "kwargs": kwargs})
        return FakeAdapter(**kwargs)

    monkeypatch.setattr(TTSAdapterFactory, "create_adapter", fake_create_adapter)

    manager = create_tts_manager(make_config(provider="edge-tts", voice=blank_voice))

    assert created == [{"name": "edge-tts", "kwargs": {"voice": DEFAULT_TTS_VOICE}}]
    assert isinstance(manager.adapter, FakeAdapter)
    assert manager.adapter.kwargs == {"voice": DEFAULT_TTS_VOICE}


def test_create_tts_manager_keeps_tts_disabled_when_adapter_initialization_fails(monkeypatch, capsys):
    def fake_create_adapter(name, **kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(TTSAdapterFactory, "create_adapter", fake_create_adapter)

    manager = create_tts_manager(make_config(provider="bad-provider"))

    assert manager.adapter is None
    assert "[TTS] 初始化失败: boom，语音功能已禁用" in capsys.readouterr().out
