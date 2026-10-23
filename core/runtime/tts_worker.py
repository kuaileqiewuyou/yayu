"""Background worker that routes LLM dialog messages through TTS handlers."""
from __future__ import annotations

import traceback
from queue import Empty, Queue

from PySide6.QtCore import QThread, Signal

from sdk.messages import LLMDialogMessage
from core.runtime.cancellation import TurnCancelled, TurnWork, turn_scope


class TTSWorker(QThread):
    """从 tts_queue 取 LLMDialogMessage，通过 handler 链处理后送入 audio_path_queue。"""

    error = Signal(str)

    def __init__(self, tts_queue: Queue, audio_path_queue: Queue):
        super().__init__()
        self.tts_queue = tts_queue
        self.audio_path_queue = audio_path_queue
        self._running = True
        self._started = False
        self._handlers = None
        self._active_token = None

    def start(self):
        self._started = True
        parent_start = getattr(super(), "start", None)
        if callable(parent_start):
            parent_start()

    def isRunning(self):
        native = getattr(super(), "isRunning", None)
        return native() if callable(native) else bool(self._started and self._running)

    def run(self):
        from core.handlers.tts_handlers import get_tts_handlers
        self._handlers = get_tts_handlers()

        while self._running:
            try:
                msg: LLMDialogMessage = self.tts_queue.get(timeout=0.5)
            except Empty:
                continue
            try:
                self._dispatch(msg)
            except TurnCancelled:
                pass
            except Exception as e:
                traceback.print_exc()
                self.error.emit(str(e))

    def _dispatch(self, msg: LLMDialogMessage) -> None:
        if isinstance(msg, TurnWork):
            self._active_token = msg.token
            try:
                with turn_scope(msg.token):
                    self._dispatch(msg.payload)
            finally:
                self._active_token = None
            return
        for handler in self._handlers:
            if handler.can_handle(msg):
                handler.pre_process(msg)
                handler.handle(msg)
                handler.post_process(msg)
                return

    def stop(self):
        self._running = False
        if self._active_token is not None:
            self._active_token.cancel()
