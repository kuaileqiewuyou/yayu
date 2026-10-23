"""GUI-thread ownership of turns, commits, stale-event filtering and shutdown."""
from __future__ import annotations

import copy
import json

from PySide6.QtCore import QObject, QTimer, Qt, Slot

from core.runtime.cancellation import TurnToken, TurnWork, discard_pending, tagged, turn_scope
from core.runtime.cg_ui_handlers import handle_t2i_image_generated


class TurnController(QObject):
    def __init__(self, window, workers, runtime_setup, history, llm_handlers, ui_handlers, audio_player, settings_window=None):
        super().__init__(window)
        self.window = window
        self.workers = workers
        self.setup = runtime_setup
        self.history = history
        self.llm_handlers = llm_handlers
        self.ui_handlers = ui_handlers
        self.audio_player = audio_player
        self.settings_window = settings_window
        self.token = None
        self.pending = False
        self.closing = False
        self.visible_dialogs = []
        self.request = None
        self.memory_service = None
        if callable(getattr(history, "get_memory_store", None)):
            from core.memory.service import MemoryService
            character_names = {getattr(c, "memory_id", ""): c.name for c in getattr(runtime_setup.runtime.config, "characters", [])}
            self.memory_service = MemoryService(history.get_memory_store(), runtime_setup.runtime.llm_manager.adapter,
                                                character_names=character_names, context_tokens=runtime_setup.runtime.llm_manager.max_tokens,
                                                session_owner=self._session_owner)
            runtime_setup.runtime.memory_service = self.memory_service
        self.close_timer = QTimer(self)
        self.close_timer.setInterval(100)
        self.close_timer.timeout.connect(self._finish_close)
        for worker in (workers.llm_worker, workers.ui_worker, getattr(workers, "t2i_worker", None)):
            if worker is not None:
                worker.turn_event.connect(self.receive, Qt.ConnectionType.QueuedConnection)
        if getattr(workers, "t2i_worker", None) is not None:
            ui_handlers.submit_t2i_prompt = lambda prompt: runtime_setup.t2i_prompt_queue.put(tagged(prompt))
        window.enqueue_turn = self.enqueue
        window.cancel_current_turn = self.cancel
        window.prepare_runtime_close = self.prepare_close
        window.stop_requested.connect(self.cancel)

    def _session_owner(self, session_id):
        session = self.history.get_session_store().get_session(session_id)
        return getattr(session, "character_id", "")

    def enqueue(self, text):
        if self.closing:
            return
        self.cancel(notify=False)
        session_id = self.history.get_active_session_id() or ""
        self.token = TurnToken(session_id)
        self.visible_dialogs = []
        messages = copy.deepcopy(self.setup.runtime.llm_manager.get_messages())
        self.request = (text, messages)
        self.pending = True
        self.window.set_waiting_for_reply(True)
        self.window.session_btn.setEnabled(True)
        self.window.stop_btn.setEnabled(True)
        self.setup.user_input_queue.put(TurnWork(self.token, self.request))

    @Slot()
    def cancel(self, *, notify=True):
        if self.token is None:
            return
        self.token.cancel()
        for queue in (self.setup.user_input_queue, self.setup.tts_queue,
                      self.setup.audio_path_queue, self.setup.t2i_prompt_queue):
            discard_pending(queue)
        stop_audio = getattr(self.audio_player, "stop", None)
        if callable(stop_audio):
            stop_audio()
        if self.pending and self.request is not None:
            # Only the GUI commits history. A cancelled worker owns a separate copy.
            manager = self.setup.runtime.llm_manager
            text, messages = self.request
            partial = "\n".join(json.dumps(msg.model_dump(by_alias=True), ensure_ascii=False)
                                for msg in self.visible_dialogs)
            note = "[本轮已停止；已完成的工具操作不会撤销。]"
            manager.set_messages([*messages, manager.build_user_message(text),
                                  {"role": "assistant", "content": partial + "\n" + note}])
        self.pending = False
        self.window.discard_stream()
        self.window.set_waiting_for_reply(False)
        self.window.stop_btn.setEnabled(False)
        self.history.save()
        if notify:
            self.window.set_reply_status("已停止本轮回复与语音")

    @Slot(object)
    def receive(self, event):
        if (self.closing or event.token is not self.token or event.token.cancelled.is_set()
                or event.token.session_id != (self.history.get_active_session_id() or "")):
            return
        with turn_scope(event.token):
            kind, payload = event.kind, event.payload
            if kind == "stream_start":
                self.llm_handlers.on_stream_start()
            elif kind == "dialog_parsed":
                self.visible_dialogs.append(payload)
                self.llm_handlers.on_dialog_parsed(payload)
            elif kind == "status_changed":
                self.window.set_reply_status(payload)
            elif kind == "tool_summary_ready":
                self.setup.runtime.llm_manager.set_messages(payload.updated_messages)
                if self.memory_service:
                    self.history.sync_memory(turn_id=event.token.id)
                self.pending = False
                self.window.set_tool_summary_result(payload)
            elif kind == "stream_end":
                self.llm_handlers.on_stream_end()
            elif kind == "error":
                self.cancel(notify=False)
                self.llm_handlers.on_llm_error(payload)
            elif kind in {"ui_scene", "ui_bgm"}:
                # Discard already-queued events from retired model controls.
                return
            elif kind.startswith("ui_"):
                handler = getattr(self.ui_handlers, "on_update_" + kind[3:])
                handler(payload)
            elif kind == "image_generated":
                handle_t2i_image_generated(self.window, payload)
            elif kind == "generation_failed":
                self.window.set_reply_status(payload, error=True)

    def prepare_close(self):
        if not self.closing:
            self.closing = True
            self.cancel(notify=False)
            if self.memory_service:
                self.memory_service.close()
            for _, worker in self.workers._iter_workers():
                worker.stop()
            self.window.set_reply_status("正在关闭，等待当前操作结束…")
            self.window.input_edit.setEnabled(False)
            self.window.send_btn.setEnabled(False)
            self.window.stop_btn.setEnabled(False)
        settings_memory = getattr(self.settings_window, "memory_tab", None)
        settings_ready = settings_memory.close_service() if settings_memory is not None else True
        if (any(worker.isRunning() for _, worker in self.workers._iter_workers())
                or (self.memory_service and self.memory_service.is_running()) or not settings_ready):
            self.close_timer.start()
            return False
        self.close_timer.stop()
        if self.settings_window is not None:
            self.settings_window.close()
        return True

    def _finish_close(self):
        if self.prepare_close():
            self.window.close()

    def shutdown(self):
        """Also handle app.quit()/event-loop errors without destroying live QThreads."""
        from PySide6.QtCore import QCoreApplication
        self.closing = True
        try:
            self.cancel(notify=False)
        finally:
            self.close_timer.stop()
            if self.memory_service:
                self.memory_service.close()
            for _, worker in self.workers._iter_workers():
                worker.stop()
            for _, worker in self.workers._iter_workers():
                while worker.isRunning():
                    worker.wait(50)
                    QCoreApplication.processEvents()
            while self.memory_service and self.memory_service.is_running():
                self.memory_service.thread.join(0.05)
                QCoreApplication.processEvents()
