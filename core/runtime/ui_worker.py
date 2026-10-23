"""Background worker that routes TTS output messages to UI update signals."""
from __future__ import annotations

from queue import Empty, Queue

from PySide6.QtCore import QThread, Signal

from core.runtime.ui_message_router import route_tts_output
from sdk.messages import TTSOutputMessage
from core.runtime.cancellation import TurnEvent, TurnWork


class UIWorker(QThread):
    """从 audio_path_queue 取 TTSOutputMessage，通过 handler 链分发 UI 更新信号。"""

    update_dialog = Signal(object)   # TTSOutputMessage - 普通对话
    update_narration = Signal(str)   # 旁白文本
    update_options = Signal(list)    # 选项列表
    update_cg = Signal(str)          # CG prompt
    update_cot = Signal(str)         # 思维链
    update_stat = Signal(str)        # 数值变化
    turn_event = Signal(object)

    def __init__(self, audio_path_queue: Queue):
        super().__init__()
        self.audio_path_queue = audio_path_queue
        self._running = True
        self._started = False

    def start(self):
        self._started = True
        parent_start = getattr(super(), "start", None)
        if callable(parent_start):
            parent_start()

    def isRunning(self):
        native = getattr(super(), "isRunning", None)
        return native() if callable(native) else bool(self._started and self._running)

    def run(self):
        while self._running:
            try:
                out: TTSOutputMessage = self.audio_path_queue.get(timeout=0.5)
            except Empty:
                continue
            self._dispatch(out)

    def _dispatch(self, out: TTSOutputMessage) -> None:
        """根据 token 类型发射对应信号。"""
        if isinstance(out, TurnWork):
            if not out.token.cancelled.is_set():
                for event in route_tts_output(out.payload):
                    self.turn_event.emit(TurnEvent(out.token, "ui_" + event.kind, event.payload))
            return
        for event in route_tts_output(out):
            if event.kind == "dialog":
                self.update_dialog.emit(event.payload)
            elif event.kind == "narration":
                self.update_narration.emit(event.payload)
            elif event.kind == "options":
                self.update_options.emit(event.payload)
            elif event.kind == "cg":
                self.update_cg.emit(event.payload)
            elif event.kind == "stat":
                self.update_stat.emit(event.payload)
            elif event.kind == "cot":
                self.update_cot.emit(event.payload)

    def stop(self):
        self._running = False
        self._started = False
