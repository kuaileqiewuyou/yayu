"""抽象消息处理器基类。"""

from __future__ import annotations
from abc import ABC, abstractmethod

from sdk.messages import LLMDialogMessage, TTSOutputMessage


class MessageHandler(ABC):
    """TTS 队列中 LLMDialogMessage 的处理器。"""

    @abstractmethod
    def can_handle(self, msg: LLMDialogMessage) -> bool: ...

    def pre_process(self, msg: LLMDialogMessage) -> None:
        pass

    def handle(self, msg: LLMDialogMessage) -> None:
        pass

    def post_process(self, msg: LLMDialogMessage) -> None:
        pass


class UIOutputMessageHandler(ABC):
    """UI 队列中 TTSOutputMessage 的处理器。"""

    @abstractmethod
    def can_handle(self, out: TTSOutputMessage) -> bool: ...

    def pre_process(self, out: TTSOutputMessage) -> None:
        pass

    def handle(self, out: TTSOutputMessage) -> None:
        pass

    def post_process(self, out: TTSOutputMessage) -> None:
        pass
