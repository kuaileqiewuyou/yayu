"""UI handler 链 — 处理 TTSOutputMessage，更新界面。"""

from __future__ import annotations
from typing import List, Callable, Any

from sdk.handlers import UIOutputMessageHandler
from sdk.messages import TTSOutputMessage
from core.messaging.dialog_tokens import (
    match_bgm, match_cg, match_choice, match_cot,
    match_narr, match_scene, match_stat,
)


class CotUiHandler(UIOutputMessageHandler):
    """思维链 — 不显示或仅调试输出。"""

    def can_handle(self, out: TTSOutputMessage) -> bool:
        return match_cot(out.name)

    def handle(self, out: TTSOutputMessage) -> None:
        pass  # 默认不显示，可由外部连接 cot_received 信号


class ChoiceUiHandler(UIOutputMessageHandler):
    def can_handle(self, out: TTSOutputMessage) -> bool:
        return match_choice(out.name)

    def handle(self, out: TTSOutputMessage) -> None:
        pass  # 由 UIWorker 信号分发


class StatUiHandler(UIOutputMessageHandler):
    def can_handle(self, out: TTSOutputMessage) -> bool:
        return match_stat(out.name)

    def handle(self, out: TTSOutputMessage) -> None:
        pass


class SceneUiHandler(UIOutputMessageHandler):
    def can_handle(self, out: TTSOutputMessage) -> bool:
        return match_scene(out.name)

    def handle(self, out: TTSOutputMessage) -> None:
        pass


class BgmUiHandler(UIOutputMessageHandler):
    def can_handle(self, out: TTSOutputMessage) -> bool:
        return match_bgm(out.name)

    def handle(self, out: TTSOutputMessage) -> None:
        pass


class CgUiHandler(UIOutputMessageHandler):
    def can_handle(self, out: TTSOutputMessage) -> bool:
        return match_cg(out.name)

    def handle(self, out: TTSOutputMessage) -> None:
        pass


class NarrUiHandler(UIOutputMessageHandler):
    def can_handle(self, out: TTSOutputMessage) -> bool:
        return match_narr(out.name)

    def handle(self, out: TTSOutputMessage) -> None:
        pass


class CharacterDialogUiHandler(UIOutputMessageHandler):
    """普通角色对话 — 兜底。"""

    def can_handle(self, out: TTSOutputMessage) -> bool:
        return True

    def handle(self, out: TTSOutputMessage) -> None:
        pass  # 由 UIWorker 信号分发


def get_ui_handlers() -> List[UIOutputMessageHandler]:
    """返回 UI handler 链。"""
    return [
        CotUiHandler(),
        ChoiceUiHandler(),
        StatUiHandler(),
        SceneUiHandler(),
        BgmUiHandler(),
        CgUiHandler(),
        NarrUiHandler(),
        CharacterDialogUiHandler(),
    ]
