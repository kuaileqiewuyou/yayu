"""聊天窗口显示辅助函数。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sdk.messages import LLMDialogMessage


def restore_chat_history_to_window(
    window: Any,
    entries: Iterable[dict],
    default_char_color: str = "#f2a0bd",
) -> None:
    """把已持久化的 UI 历史恢复显示到聊天窗口。"""
    for entry in entries:
        role = entry.get("role")
        text = entry.get("content") or ""
        if not text:
            continue
        if entry.get("kind") == "card" and hasattr(window, "add_card"):
            window.add_card(text)
        elif role == "user":
            window.add_message(text, is_user=True, char_color=default_char_color)
        elif role == "assistant":
            window.add_message(
                text,
                is_user=False,
                char_name=entry.get("name", ""),
                char_color=default_char_color,
            )
        elif role == "system":
            window.add_message(
                text,
                is_user=False,
                char_name=entry.get("name", "系统"),
                char_color=entry.get("color", "#84C2D5"),
            )


def display_assistant_dialog(
    window: Any,
    dialog: LLMDialogMessage,
    char_color: str = "#f2a0bd",
) -> None:
    """显示一条普通角色对话。"""
    window.add_message(dialog.text or "", is_user=False, char_name=dialog.name, char_color=char_color)
