from dataclasses import dataclass, field

from core.runtime.llm_setup import LLMRuntimeContext, create_llm_runtime_context
from llm.llm_adapter import LLMAdapterFactory


@dataclass
class FakeApiConfig:
    temperature: float = 0.7


@dataclass
class FakeCharacter:
    name: str = "爱丽丝"
    color: str = "#AA00FF"
    character_setting: str = "角色设定"
    emotion_tags: str = "开心,难过"
    default_skills: list = field(default_factory=list)


@dataclass
class FakeBackground:
    name: str = "教室"
    bg_tags: str = "白天"
    bgm_tags: str = "轻快"


@dataclass
class FakeConfig:
    api_config: FakeApiConfig = field(default_factory=FakeApiConfig)
    characters: list = field(default_factory=list)
    backgrounds: list = field(default_factory=list)
    skills_root: str = "."
    system_config: object = field(default_factory=lambda: type("SystemConfig", (), {"default_skills": []})())

    def merged_llm_factory_kwargs(self):
        return {
            "llm_provider": "fake-provider",
            "api_key": "fake-key",
            "base_url": "http://llm.local",
            "model": "fake-model",
        }


class FakeAdapter:
    def chat(self, messages: list, stream: bool = False, **kwargs):
        return None


def test_create_llm_runtime_context_uses_defaults_without_characters(monkeypatch):
    created = []

    def fake_create_adapter(**kwargs):
        created.append(kwargs)
        return FakeAdapter()

    monkeypatch.setattr(LLMAdapterFactory, "create_adapter", fake_create_adapter)

    context = create_llm_runtime_context(FakeConfig(api_config=FakeApiConfig(temperature=0.33)))

    assert isinstance(context, LLMRuntimeContext)
    assert created == [
        {
            "llm_provider": "fake-provider",
            "api_key": "fake-key",
            "base_url": "http://llm.local",
            "model": "fake-model",
        }
    ]
    assert context.active_character_name == "角色"
    assert context.active_character_color == "#f2a0bd"
    assert context.manager.adapter.__class__ is FakeAdapter
    assert context.manager.user_template == ""
    assert context.manager.get_messages() == []
    assert context.manager.generation_config == {"temperature": 0.33, "max_tokens": 4096}


def test_create_llm_runtime_context_uses_first_character_and_first_background(monkeypatch):
    adapter = FakeAdapter()
    generated = []

    monkeypatch.setattr(LLMAdapterFactory, "create_adapter", lambda **kwargs: adapter)
    monkeypatch.setattr("core.runtime.llm_setup.build_session_skills_context", lambda *args, **kwargs: "")

    def fake_generate_system_prompt(character, background, skills_context=""):
        generated.append({"character": character, "background": background})
        return f"prompt for {character.name} at {background.name}"

    monkeypatch.setattr("core.runtime.llm_setup.generate_system_prompt", fake_generate_system_prompt)

    first_character = FakeCharacter(name="小春", color="#123456")
    second_character = FakeCharacter(name="不应使用", color="#000000")
    first_background = FakeBackground(name="公园")
    second_background = FakeBackground(name="不应使用")
    config = FakeConfig(
        api_config=FakeApiConfig(temperature=0.91),
        characters=[first_character, second_character],
        backgrounds=[first_background, second_background],
    )

    context = create_llm_runtime_context(config)

    assert generated == [{"character": first_character, "background": first_background}]
    assert context.active_character_name == "小春"
    assert context.active_character_color == "#123456"
    assert context.manager.adapter is adapter
    assert context.manager.user_template == "prompt for 小春 at 公园"
    assert context.manager.get_messages() == [
        {"role": "system", "content": "prompt for 小春 at 公园"}
    ]
    assert context.manager.generation_config == {"temperature": 0.91, "max_tokens": 4096}


def test_create_llm_runtime_context_passes_none_background_when_no_backgrounds(monkeypatch):
    monkeypatch.setattr(LLMAdapterFactory, "create_adapter", lambda **kwargs: FakeAdapter())
    generated = []
    monkeypatch.setattr("core.runtime.llm_setup.build_session_skills_context", lambda *args, **kwargs: "")

    def fake_generate_system_prompt(character, background, skills_context=""):
        generated.append({"character": character, "background": background})
        return "prompt without background"

    monkeypatch.setattr("core.runtime.llm_setup.generate_system_prompt", fake_generate_system_prompt)

    character = FakeCharacter(name="无背景角色", color="#FEDCBA")
    context = create_llm_runtime_context(
        FakeConfig(characters=[character], backgrounds=[])
    )

    assert generated == [{"character": character, "background": None}]
    assert context.active_character_name == "无背景角色"
    assert context.active_character_color == "#FEDCBA"
    assert context.manager.user_template == "prompt without background"
