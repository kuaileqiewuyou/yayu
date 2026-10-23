"""Background worker that streams LLM responses into dialog messages."""
from __future__ import annotations

import traceback
import copy
from queue import Empty, Queue

from PySide6.QtCore import QThread, Signal

from core.messaging.stream_parser import LlmResponseStreamParser
from core.runtime.agent_runtime import run_user_turn
from core.runtime.app_runtime import try_get_app_runtime
from core.runtime.character_selection import get_active_character
from sdk.messages import LLMDialogMessage
from core.runtime.cancellation import (
    TurnCancelled, TurnEvent, TurnWork, check_cancelled, current_token, tagged, turn_scope,
)


def _active_character_name(rt) -> str:
    character = get_active_character(rt.config) if rt and rt.config else None
    if character is not None:
        return character.name
    return "角色"


def _plain_text_to_dialog(text: str, rt) -> LLMDialogMessage:
    return LLMDialogMessage(name=_active_character_name(rt), text=text, asset_id="-1")


def _safe_bad_llm_output_to_dialog(rt) -> LLMDialogMessage:
    return _plain_text_to_dialog(
        "模型回复格式异常，我先把这次回复安全收住了。请稍后重试，或检查角色模板的输出格式。",
        rt,
    )


class LLMWorker(QThread):
    """从 user_input_queue 取用户输入，流式调用 LLM，逐条解析 JSON 对象送入 tts_queue。"""

    status_changed = Signal(str)
    stream_start = Signal()
    stream_chunk = Signal(str)
    dialog_parsed = Signal(object)  # LLMDialogMessage
    tool_summary_ready = Signal(object)
    stream_end = Signal()
    error = Signal(str)
    turn_event = Signal(object)

    def __init__(self, user_input_queue: Queue, tts_queue: Queue):
        super().__init__()
        self.user_input_queue = user_input_queue
        self.tts_queue = tts_queue
        self._running = True
        self._started = False
        self._active_token = None

    def start(self):
        self._started = True
        parent_start = getattr(super(), "start", None)
        if callable(parent_start):
            parent_start()

    def isRunning(self):
        native = getattr(super(), "isRunning", None)
        return native() if callable(native) else bool(self._started and self._running)

    def _emit(self, kind, payload=None):
        check_cancelled()
        token = current_token()
        if token is not None:
            self.turn_event.emit(TurnEvent(token, kind, payload))
            return
        signal = getattr(self, kind, None)
        if signal is not None:
            signal.emit() if payload is None else signal.emit(payload)

    def _handle_user_text_once(self, user_text: str) -> None:
        if isinstance(user_text, TurnWork):
            self._active_token = user_text.token
            try:
                with turn_scope(user_text.token):
                    self._handle_turn(*user_text.payload)
            except TurnCancelled:
                pass
            except Exception as exc:
                if not user_text.token.cancelled.is_set():
                    self.turn_event.emit(TurnEvent(user_text.token, "error", str(exc)))
            finally:
                self._active_token = None
            return
        self._handle_turn(user_text)

    def _handle_turn(self, user_text, initial_messages=None) -> None:
        rt = try_get_app_runtime()
        if rt is None:
            return
        manager = rt.llm_manager
        if initial_messages is not None:
            manager = copy.copy(manager)
            manager.set_messages(copy.deepcopy(initial_messages))
        self._emit("status_changed", "模型思考中...")
        self._emit("stream_start")
        from llm.compact_manager import CompactManager
        if not hasattr(self, '_compact'):
            self._compact = CompactManager(
                max_tokens=rt.llm_manager.max_tokens)
        raw_messages = manager.get_messages()
        memory = getattr(rt, "memory_service", None)
        token = current_token()
        tool_manager = getattr(rt, "tool_manager", None)
        definitions = tool_manager.get_tool_definitions() if tool_manager else []
        if memory and token:
            request_messages = memory.prepare_context(token.session_id, manager, user_text, definitions)
        else:
            request_messages = self._compact.build_context(
                raw_messages, user_message=manager.build_user_message(user_text), tools=definitions,
                reply_tokens=manager.get_generation_config().get("max_tokens", 4096))
        manager = copy.copy(manager)
        manager.set_messages(request_messages)

        parser = LlmResponseStreamParser()
        parsed_count = 0
        streamed_text = ""

        def on_text(chunk):
            nonlocal parser, parsed_count, streamed_text
            check_cancelled()
            if chunk is None:
                parser = LlmResponseStreamParser()
                parsed_count = 0
                streamed_text = ""
                return
            streamed_text += chunk
            self._emit("stream_chunk", chunk)
            for msg in parser.feed(chunk):
                parsed_count += 1
                self._emit("dialog_parsed", msg)
                self.tts_queue.put(tagged(msg))

        tool_manager = getattr(rt, "tool_manager", None)
        turn_kwargs = dict(
            llm_manager=manager,
            tool_manager=tool_manager,
            user_text=user_text,
            progress_callback=lambda text: self._emit("status_changed", text),
        )
        if callable(getattr(manager.adapter, "generate_stream", None)):
            turn_kwargs["text_callback"] = on_text
        result = run_user_turn(**turn_kwargs)
        # Only new messages belong in the durable log. Retrieved facts and
        # summaries are ephemeral request data, never fake user turns.
        result.updated_messages = raw_messages + result.updated_messages[len(request_messages):]
        manager.set_messages(result.updated_messages)
        if initial_messages is None:
            rt.llm_manager.set_messages(result.updated_messages)
        self._emit("status_changed", "正在回复...")
        if streamed_text != result.final_output:
            on_text(None)
            on_text(result.final_output)
        if parsed_count == 0 and result.final_output.strip():
            if parser.has_errors or result.final_output.lstrip().startswith(("{", "[", "```")):
                msg = _safe_bad_llm_output_to_dialog(rt)
            else:
                msg = _plain_text_to_dialog(result.final_output.strip(), rt)
            self._emit("dialog_parsed", msg)
            self.tts_queue.put(tagged(msg))
        self._emit("tool_summary_ready", result)
        self._emit("status_changed", "")
        self._emit("stream_end")
        if parser.has_errors:
            print(f"[LLMWorker] 解析警告: {parser.last_error}")

    def run(self):
        while self._running:
            try:
                user_text = self.user_input_queue.get(timeout=0.5)
            except Empty:
                continue
            try:
                self._handle_user_text_once(user_text)
            except Exception as e:
                traceback.print_exc()
                self.status_changed.emit(f"回复失败：{e}")
                self.error.emit(str(e))

    def stop(self):
        self._running = False
        if self._active_token is not None:
            self._active_token.cancel()
