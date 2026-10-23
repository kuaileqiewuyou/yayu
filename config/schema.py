"""应用配置的 Pydantic 数据模型定义。"""
from pydantic import BaseModel, Field, BeforeValidator, field_validator, model_validator
from pydantic_core import PydanticUseDefault
from typing import List, Dict, Optional, Union, Any, Annotated, TypeVar
from uuid import uuid4

from core.mcp.config import MCPServerConfig


def default_if_none(value: Any) -> Any:
    """YAML 中 None 值时使用字段默认值。"""
    if value is None:
        raise PydanticUseDefault()
    return value


T = TypeVar("T")
DefaultIfNone = Annotated[T, BeforeValidator(default_if_none)]
DEFAULT_TTS_VOICE = "zh-CN-XiaoyiNeural"


class Sprite(BaseModel):
    """单个立绘/语音配置"""
    id: Optional[int] = Field(default=None, ge=0, description="稳定立绘编号，从 0 开始且不随列表顺序变化")
    path: str = Field(..., description="立绘图片路径")
    voice_path: Optional[str] = Field(None, description="语音文件路径")
    voice_text: Optional[str] = Field(None, description="语音对应文本")


class EmotionItem(BaseModel):
    """结构化情绪 / 立绘项。"""
    id: int = Field(..., description="情绪编号，从 1 开始")
    label: str = Field(..., description="情绪标签")
    sprite_path: str = Field(..., description="该情绪对应的立绘路径")

    @field_validator("id")
    @classmethod
    def _normalize_legacy_zero_id(cls, value: int) -> int:
        return 1 if value == 0 else value


class Character(BaseModel):
    """角色配置"""
    memory_id: str = Field(default_factory=lambda: uuid4().hex, description="稳定的角色记忆标识，改名时保留")
    name: str = Field(..., description="角色名称")
    color: str = Field(default="#FFFFFF", description="角色颜色")
    avatar: DefaultIfNone[str] = Field(default="", description="角色显式头像路径")
    default_skills: DefaultIfNone[List[str]] = Field(default_factory=list, description="角色默认启用的 skills")
    sprite_prefix: str = Field(default="", description="立绘文件名前缀")
    sprites: DefaultIfNone[List[Union[Sprite, dict]]] = Field(default_factory=list)
    emotion_items: DefaultIfNone[List[Union[EmotionItem, dict]]] = Field(default_factory=list, description="结构化情绪 / 立绘项")
    character_setting: DefaultIfNone[str] = Field(default="", description="角色设定描述")
    sprite_scale: DefaultIfNone[float] = Field(default=1.0, description="立绘缩放")

    emotion_tags: DefaultIfNone[str] = Field(default="", description="情绪标签")

    @model_validator(mode="after")
    def _assign_stable_sprite_ids(self):
        """旧配置首次加载时按当前顺序固化编号；已有合法编号永不重排。"""
        assigned_ids: list[int | None] = []
        used_ids: set[int] = set()
        for sprite in self.sprites:
            raw_id = sprite.get("id") if isinstance(sprite, dict) else getattr(sprite, "id", None)
            try:
                sprite_id = int(raw_id) if raw_id is not None else None
            except (TypeError, ValueError):
                sprite_id = None
            if sprite_id is None or sprite_id < 0 or sprite_id in used_ids:
                assigned_ids.append(None)
                continue
            assigned_ids.append(sprite_id)
            used_ids.add(sprite_id)

        next_available = max(used_ids, default=-1) + 1
        for index, sprite_id in enumerate(assigned_ids):
            if sprite_id is not None:
                continue
            while next_available in used_ids:
                next_available += 1
            assigned_ids[index] = next_available
            used_ids.add(next_available)
            next_available += 1

        for sprite, sprite_id in zip(self.sprites, assigned_ids):
            if isinstance(sprite, dict):
                sprite["id"] = sprite_id
            else:
                sprite.id = sprite_id
        return self

    @property
    def primary_sprite_path(self) -> str:
        if self.emotion_items:
            normalized_items = []
            for item in self.emotion_items:
                item_id = item.id if isinstance(item, EmotionItem) else item.get("id", 0)
                sprite_path = item.sprite_path if isinstance(item, EmotionItem) else item.get("sprite_path", "")
                normalized_items.append((item_id, sprite_path))
            normalized_items.sort(key=lambda pair: pair[0])
            for item_id, sprite_path in normalized_items:
                if item_id >= 1 and sprite_path:
                    return sprite_path
        return ""

    refer_audio_path: Optional[str] = Field(default="")
    prompt_text: Optional[str] = Field(default="")
    prompt_lang: Optional[str] = Field(default="zh")
    speech_speed: DefaultIfNone[float] = Field(default=1.0)
    speech_volume: DefaultIfNone[float] = Field(default=1.0)


class MediaAssetBinding(BaseModel):
    """A background image and its user-visible name."""

    path: str = Field(..., description="本地资源路径")
    label: str = Field(default="", description="资源名称，与文件一一对应")


class Background(BaseModel):
    """背景配置"""
    name: str = Field(..., description="背景组名称")
    sprite_prefix: str = Field(default="")
    sprites: DefaultIfNone[List[Union[Sprite, dict]]] = Field(default_factory=list)
    bg_tags: DefaultIfNone[str] = Field(default="")
    # Legacy BGM values remain readable so older configs load without data loss.
    # No UI, playback or AI control reads these fields.
    bgm_list: Optional[List[str]] = Field(default_factory=list)
    bgm_tags: DefaultIfNone[str] = Field(default="")
    scene_bindings: DefaultIfNone[List[MediaAssetBinding]] = Field(default_factory=list)
    bgm_bindings: DefaultIfNone[List[MediaAssetBinding]] = Field(default_factory=list)


class ApiConfig(BaseModel):
    """API 配置"""
    # TTS
    gpt_sovits_api_path: DefaultIfNone[str] = Field(default="")
    gpt_sovits_url: DefaultIfNone[str] = Field(default="")
    tts_provider: DefaultIfNone[str] = Field(default="none")
    tts_speed: DefaultIfNone[float] = Field(default=1.0)
    tts_voice: DefaultIfNone[str] = Field(default=DEFAULT_TTS_VOICE)
    # LLM
    llm_api_key: DefaultIfNone[Dict[str, str]] = Field(default_factory=dict)
    llm_base_url: DefaultIfNone[str] = Field(default="")
    llm_model: DefaultIfNone[Dict[str, str]] = Field(default_factory=dict)
    llm_provider: DefaultIfNone[str] = Field(default="OpenAI")
    is_streaming: DefaultIfNone[bool] = Field(default=True)
    temperature: DefaultIfNone[float] = Field(default=0.7)
    repetition_penalty: DefaultIfNone[float] = Field(default=1.0)
    presence_penalty: DefaultIfNone[float] = Field(default=0.0)
    frequency_penalty: DefaultIfNone[float] = Field(default=0.0)
    max_context_tokens: DefaultIfNone[int] = Field(default=128000)
    # Free web search (DDGS + local HTTP extraction)
    web_search_enabled: DefaultIfNone[bool] = Field(default=True)
    web_search_region: DefaultIfNone[str] = Field(default="cn-zh")
    web_search_safesearch: DefaultIfNone[str] = Field(default="moderate")
    web_search_max_results: DefaultIfNone[int] = Field(default=5, ge=1, le=10)
    web_extract_timeout_seconds: DefaultIfNone[int] = Field(default=15, ge=5, le=60)
    web_extract_max_chars: DefaultIfNone[int] = Field(default=12000, ge=1000, le=50000)
    web_search_max_calls: DefaultIfNone[int] = Field(default=5, ge=1, le=50)
    web_extract_max_calls: DefaultIfNone[int] = Field(default=3, ge=1, le=50)
    # T2I
    t2i_provider: DefaultIfNone[str] = Field(default="none")
    t2i_api_url: DefaultIfNone[str] = Field(default="http://127.0.0.1:8188")
    t2i_checkpoint: DefaultIfNone[str] = Field(default="v1-5-pruned-emaonly.ckpt")


class SkillPreset(BaseModel):
    """命名技能组合。"""
    name: str = Field(..., description="技能组合名称")
    skills: DefaultIfNone[List[str]] = Field(default_factory=list, description="组合中的技能名称")


class SystemConfig(BaseModel):
    """系统配置"""
    active_character_id: DefaultIfNone[str] = Field(default="", description="当前聊天角色的稳定 memory_id；旧配置为空时使用首个角色")
    ui_language: DefaultIfNone[str] = Field(default="zh_CN")
    voice_language: DefaultIfNone[str] = Field(default="ja")
    theme: DefaultIfNone[str] = Field(default="dark")
    font_size: DefaultIfNone[int] = Field(default=14)
    background_path: DefaultIfNone[str] = Field(default="")
    always_on_top: DefaultIfNone[bool] = Field(default=False, description="主界面始终显示在其他应用窗口上方")
    bgm_path: DefaultIfNone[str] = Field(default="")
    skills_root: DefaultIfNone[str] = Field(default="data/skills")
    default_skills: DefaultIfNone[List[str]] = Field(default_factory=list, description="全局默认启用的 skills")
    skill_presets: DefaultIfNone[List[SkillPreset]] = Field(default_factory=list)
    reduce_motion: DefaultIfNone[bool] = Field(default=False, description="减少动效：关闭立绘呼吸、逐字显示等动画")
    typewriter_enabled: DefaultIfNone[bool] = Field(default=True, description="台词逐字显示")
    typewriter_cps: DefaultIfNone[int] = Field(default=40, description="逐字显示速度（字/秒）")


class AppConfig(BaseModel):
    """应用总配置"""
    api_config: ApiConfig = Field(default_factory=ApiConfig)
    system_config: SystemConfig = Field(default_factory=SystemConfig)
    characters: List[Character] = Field(default_factory=list)
    backgrounds: List[Background] = Field(default_factory=list)
    mcp_servers: List[MCPServerConfig] = Field(default_factory=list)
