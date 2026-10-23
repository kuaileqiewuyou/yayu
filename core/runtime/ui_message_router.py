"""纯函数 UI 消息路由器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.messaging.dialog_tokens import (
    match_bgm,
    match_card,
    match_cg,
    match_choice,
    match_cot,
    match_narr,
    match_scene,
    match_stat,
)
from core.runtime.display_logic import should_display_llm_message
from sdk.messages import LLMDialogMessage, TTSOutputMessage


@dataclass(frozen=True)
class UiEvent:
    """UI 层可消费的事件，不依赖 Qt。"""

    kind: str
    payload: Any
    message: LLMDialogMessage | TTSOutputMessage | None = None


def _split_options(text: str | None) -> list[str]:
    return [option.strip() for option in (text or "").split("/") if option.strip()]


def route_llm_dialog(msg: LLMDialogMessage, active_character_name: str) -> list[UiEvent]:
    """将 LLM 解析出的 dialog 消息路由为即时 UI 事件。

    LLM 即时阶段只显示普通角色对话；控制 token 由 TTS/UIWorker
    阶段统一分发，避免 CHOICE/NARR 等内容重复显示。
    """
    name = msg.name

    if match_scene(name) or match_bgm(name):
        # Old prompts/history may still produce these retired controls.
        return []
    if match_cot(name):
        return []
    if match_choice(name):
        return []
    if match_narr(name):
        return []
    if match_card(name):
        # 卡片不需要语音，解析完成即显示，保证与台词顺序一致。
        return [UiEvent("card", msg.text or "", msg)]
    if should_display_llm_message(msg, active_character_name):
        return [UiEvent("dialog", msg, msg)]
    return []


def route_tts_output(out: TTSOutputMessage) -> list[UiEvent]:
    """将 TTS 输出消息路由为 UI 事件。"""
    name = out.name
    text = out.text or ""

    if match_cot(name):
        return [UiEvent("cot", text, out)]
    if match_choice(name):
        return [UiEvent("options", _split_options(text), out)]
    if match_scene(name) or match_bgm(name):
        # Background selection is manual; music playback has been removed.
        return []
    if match_cg(name):
        return [UiEvent("cg", text, out)]
    if match_stat(name):
        return [UiEvent("stat", text, out)]
    if match_card(name):
        # 已在 LLM 即时阶段显示，这里不重复。
        return []
    if match_narr(name):
        return [UiEvent("narration", text, out)]
    return [UiEvent("dialog", out, out)]
