"""LLM Worker 信号到聊天窗口的 UI 处理器。"""

from __future__ import annotations

from typing import Any, Callable

from core.messaging.dialog_tokens import CARD
from core.runtime.chat_display import display_assistant_dialog
from core.runtime.ui_message_router import route_llm_dialog
from sdk.messages import LLMDialogMessage


class LLMUiHandlers:
    """封装 LLM worker 信号对应的聊天窗口更新逻辑。"""

    def __init__(
        self,
        window: Any,
        history: Any,
        active_character_name: str,
        char_color: str,
        set_sprite_by_id: Callable[[str], None],
    ) -> None:
        self.window = window
        self.history = history
        self.active_character_name = active_character_name
        self.char_color = char_color
        self.set_sprite_by_id = set_sprite_by_id

    def on_stream_start(self) -> None:
        """开始 LLM 流式回复。"""
        self.window.begin_stream(
            char_name=self.active_character_name,
            char_color=self.char_color,
        )

    def on_dialog_parsed(self, msg: LLMDialogMessage) -> None:
        """每解析出一条 dialog 就立即更新 UI（不等 TTS）。"""
        events = route_llm_dialog(msg, self.active_character_name)
        if not events:
            return

        # 丢弃协议层流式原文，改为逐条显示解析后的正式对白。
        getattr(self.window, "discard_stream", self.window.end_stream)()
        for event in events:
            if event.kind == "dialog":
                dialog = event.payload
                display_assistant_dialog(self.window, dialog, char_color=self.char_color)
                self.set_sprite_by_id(str(dialog.asset_id))
                self.history.add_to_history(
                    "assistant",
                    dialog.text or "",
                    name=dialog.name,
                    asset_id=str(dialog.asset_id),
                )
            elif event.kind == "card":
                markdown = event.payload
                if not markdown.strip():
                    continue
                self.window.add_card(markdown)
                self.history.add_to_history("assistant", markdown, name=CARD, kind="card")

    def on_stream_end(self) -> None:
        """结束 LLM 流式回复。"""
        self.window.end_stream()
        self.window.set_waiting_for_reply(False)
        self.history.save()

    def on_llm_error(self, err: str) -> None:
        """显示 LLM 错误并恢复窗口输入状态。"""
        self.window.end_stream()
        self.window.set_waiting_for_reply(False)
        self.window.add_message(
            f"[错误] {err}",
            is_user=False,
            char_name="系统",
            char_color="#FF4444",
        )
