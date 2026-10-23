"""队列消息 Pydantic 模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Union


class UserInputMessage(BaseModel):
    """用户输入队列的消息格式。"""
    text: str = Field(..., description="用户输入的聊天文本")


class LLMDialogMessage(BaseModel):
    """
    LLM 输出的单条对话片段。

    character_name 字段用保留字区分消息类型：
    - 普通角色名 → 对话 + 立绘切换
    - COT/NARR/CHOICE/STAT/SCENE/BGM/CG → 系统指令
    """
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., alias="character_name", description="角色名或系统保留字")
    text: Optional[str] = Field("", alias="speech", description="台词/内容")
    asset_id: Optional[Union[str, int]] = Field("-1", alias="sprite", description="立绘索引/BGM索引，-1表示不变")
    translate: Optional[str] = Field("", description="翻译文本")
    effect: Optional[str] = Field("", description="特效名称")


class TTSOutputMessage(BaseModel):
    """TTS 处理后输出的 UI 队列消息。"""
    model_config = ConfigDict(populate_by_name=True)

    audio_path: str = Field("", description="语音文件路径")
    name: str = Field(..., alias="character_name", description="角色名")
    text: Optional[str] = Field("", alias="speech", description="台词")
    asset_id: Optional[Union[str, int]] = Field("-1", alias="sprite", description="立绘索引")
    effect: Optional[str] = Field("", description="特效名称")
    error: Optional[str] = Field("", description="TTS 或播放阶段的非致命错误信息")
    is_system_message: bool = Field(False, description="是否为系统消息")
    is_final_segment: bool = Field(True, description="是否为最后一段")
