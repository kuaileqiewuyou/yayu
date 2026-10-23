"""LLM 运行时初始化辅助。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from llm.llm_adapter import LLMAdapterFactory
from llm.llm_manager import LLMManager
from llm.template_generator import generate_system_prompt
from core.skills.runtime import build_session_skills_context
from core.runtime.character_selection import get_active_character


@dataclass
class LLMRuntimeContext:
    """LLM manager 及当前活动角色 UI 上下文。"""

    manager: LLMManager
    active_character_name: str
    active_character_color: str


def build_active_character_template(config: Any) -> str:
    """Build a fresh persona prompt for the selected stable character identity."""
    character = get_active_character(config)
    if character is None:
        return ""
    skills_context = build_session_skills_context(
        config.skills_root,
        global_default_skills=config.system_config.default_skills,
        character_default_skills=character.default_skills,
    )
    background = config.backgrounds[0] if config.backgrounds else None
    return generate_system_prompt(character=character, background=background, skills_context=skills_context)


def create_llm_runtime_context(config: Any) -> LLMRuntimeContext:
    """根据配置创建 LLM manager，并提取当前活动角色上下文。"""
    llm_kwargs = config.merged_llm_factory_kwargs()
    adapter = LLMAdapterFactory.create_adapter(**llm_kwargs)

    character_template = build_active_character_template(config)
    char_name = "角色"
    char_color = "#f2a0bd"
    char = get_active_character(config)
    if char is not None:
        char_name = char.name
        char_color = char.color

    llm_manager = LLMManager(
        adapter=adapter,
        user_template=character_template,
        max_tokens=getattr(config.api_config, "max_context_tokens", 128000),
        generation_config={
            "temperature": config.api_config.temperature,
            "max_tokens": 4096,
        },
    )

    return LLMRuntimeContext(
        manager=llm_manager,
        active_character_name=char_name,
        active_character_color=char_color,
    )
