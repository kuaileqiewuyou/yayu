"""Background worker for text-to-image generation requests."""
from __future__ import annotations

from queue import Empty, Queue

from PySide6.QtCore import QThread, Signal
from core.runtime.cancellation import TurnCancelled, TurnEvent, TurnWork, turn_scope


class T2IWorker(QThread):
    """从 t2i_prompt_queue 取 CG prompt，在后台调用 T2I manager。"""

    image_generated = Signal(str)
    generation_failed = Signal(str)
    turn_event = Signal(object)

    def __init__(self, t2i_prompt_queue: Queue, t2i_manager):
        super().__init__()
        self.t2i_prompt_queue = t2i_prompt_queue
        self.t2i_manager = t2i_manager
        self._running = True
        self._active_token = None

    def run(self):
        while self._running:
            try:
                prompt = self.t2i_prompt_queue.get(timeout=0.5)
            except Empty:
                continue
            self._dispatch(prompt)

    def _dispatch(self, prompt: str) -> None:
        if isinstance(prompt, TurnWork):
            self._active_token = prompt.token
            try:
                with turn_scope(prompt.token):
                    path = self.t2i_manager.generate_image(prompt.payload)
                    prompt.token.check()
                    kind = "image_generated" if path else "generation_failed"
                    self.turn_event.emit(TurnEvent(prompt.token, kind, path or "CG 生成未返回图片"))
            except TurnCancelled:
                pass
            except Exception as exc:
                if not prompt.token.cancelled.is_set():
                    self.turn_event.emit(TurnEvent(prompt.token, "generation_failed", f"CG 生成失败：{exc}"))
            finally:
                self._active_token = None
            return
        try:
            image_path = self.t2i_manager.generate_image(prompt)
        except Exception as e:
            self.generation_failed.emit(f"CG 生成失败：{e}")
            return
        if image_path:
            self.image_generated.emit(image_path)
        else:
            self.generation_failed.emit("CG 生成未返回图片")

    def stop(self, wait_ms: int | None = None):
        self._running = False
        if self._active_token is not None:
            self._active_token.cancel()
        if wait_ms is not None:
            self.wait(wait_ms)
