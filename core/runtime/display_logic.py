"""消息显示逻辑辅助函数。"""

from __future__ import annotations

from core.messaging.dialog_tokens import is_system_token, match_narr


def should_display_llm_message(msg, active_character_name: str) -> bool:
    """判断 LLM 解析出的消息是否应该立即显示到聊天气泡。"""
    name = getattr(msg, "name", "")
    if match_narr(name):
        return True
    if is_system_token(name):
        return False
    return name == active_character_name or not getattr(msg, "is_system_message", False)
