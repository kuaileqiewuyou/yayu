"""Offline real-Qt integration check; all history is kept in a temporary directory."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont
from core.runtime.app_runtime import clear_app_runtime
from core.runtime.cancellation import TurnEvent, TurnWork, check_cancelled, run_async
from core.runtime.runtime_setup import create_runtime_setup
from core.runtime.worker_lifecycle import create_runtime_workers
from core.runtime.signal_wiring import wire_runtime_signals
from core.sprite import chat_history
from core.sessions.store import SessionStore
from llm.llm_manager import LLMManager
from llm.tools.tool_manager import ToolManager
from sdk.messages import LLMDialogMessage, TTSOutputMessage
from ui.chat_ui.chat_ui import ChatUIWindow


def pump(app, predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting for Qt/worker state")
        time.sleep(0.005)
    app.processEvents()


class Adapter:
    mode = "complete"

    def generate_stream(self, messages, *, tools, generation_config, on_text):
        mode = self.mode
        first = json.dumps({"character_name": "Test", "speech": mode + ":first", "sprite": "-1"})
        second = json.dumps({"character_name": "Test", "speech": mode + ":second", "sprite": "-1"})
        on_text(first[:25])
        on_text(first[25:])
        if mode != "complete":
            while True:
                check_cancelled()
                time.sleep(0.01)
        on_text("\n" + second)
        return {"content": first + "\n" + second, "tool_calls": []}


class WaitingMedia:
    def __init__(self):
        self.started = threading.Event()
        self.cleaned = threading.Event()

    def wait(self):
        async def operation():
            self.started.set()
            try:
                await asyncio.sleep(30)
            finally:
                self.cleaned.set()
        return run_async(operation)

    def synthesize(self, *args, **kwargs):
        return self.wait()

    def generate_image(self, *args, **kwargs):
        return self.wait()


def main():
    app = QApplication([])
    if os.name == "nt":
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))
            app.setFont(QFont("Microsoft YaHei", 10))
    app.setQuitOnLastWindowClosed(False)
    with tempfile.TemporaryDirectory(prefix="galgame-stream-smoke-") as temp:
        root = Path(temp)
        chat_history.set_session_store(SessionStore(
            history_root=root, sessions_dir=root / "sessions", index_path=root / "sessions.json",
            legacy_default_file=root / "default.json",
        ))
        adapter = Adapter()
        manager = LLMManager(adapter, user_template="Reply in JSON")
        config = NS(characters=[NS(name="Test")], backgrounds=[], default_skills=[], skill_presets=[])
        setup = create_runtime_setup(config, manager, None)
        setup.runtime.tool_manager = ToolManager()
        chat_history.ensure_default_session()
        chat_history.load_session(chat_history.get_active_session_id())
        cg = WaitingMedia()
        workers = create_runtime_workers(setup, cg)
        window = ChatUIWindow()
        played = []
        stopped = []
        handles = wire_runtime_signals(
            window=window, workers=workers, runtime_setup=setup,
            llm_context=NS(active_character_name="Test", active_character_color="#ABCDEF"),
            chat_history=chat_history, config=config,
            sprite_controller=NS(set_sprite_by_id=lambda _: None),
            audio_player=NS(play=lambda path: played.append(path), stop=lambda: stopped.append(True)),
        )
        controller = handles.turn_controller

        def send(text):
            window.input_edit.setText(text)
            window.send_btn.click()

        def visible(text):
            return any(entry["text"] == text for entry in window.message_history_snapshot())

        workers.start_all()
        window.show()
        try:
            send("complete")
            pump(app, lambda: visible("complete:second") and not window._waiting_for_reply)
            assert [entry["text"] for entry in window.message_history_snapshot()][-2:] == ["complete:first", "complete:second"]
            assert len([m for m in manager.get_messages() if m["role"] == "assistant"]) == 1

            adapter.mode = "stop"
            send("stop")
            pump(app, lambda: visible("stop:first"))
            assert window._waiting_for_reply and window.stop_btn.isEnabled()
            assert window.session_btn.isEnabled()
            old_token = controller.token
            window.stop_btn.click()
            pump(app, lambda: workers.llm_worker._active_token is None)
            assert old_token.cancelled.is_set()
            assert not window._waiting_for_reply and window.send_btn.isEnabled()
            assert not visible("stop:second") and visible("stop:first")
            assert stopped

            adapter.mode = "switch"
            send("switch")
            pump(app, lambda: visible("switch:first"))
            old_token = controller.token
            old_id = chat_history.get_active_session_id()
            window.new_session_requested.emit("全局默认")
            pump(app, lambda: workers.llm_worker._active_token is None)
            assert old_token.cancelled.is_set()
            assert chat_history.get_active_session_id() != old_id
            assert manager.get_messages() == [{"role": "system", "content": "Reply in JSON"}]
            assert window.message_history_snapshot() == []

            adapter.mode = "current"
            send("current")
            pump(app, lambda: visible("current:first"))
            before = list(window.message_history_snapshot())
            for event in [
                TurnEvent(old_token, "dialog_parsed", LLMDialogMessage(name="Test", text="STALE")),
                TurnEvent(old_token, "stream_end"),
                TurnEvent(old_token, "error", "STALE ERROR"),
                TurnEvent(old_token, "ui_dialog", TTSOutputMessage(name="Test", audio_path="STALE.wav")),
                TurnEvent(old_token, "ui_narration", "STALE NARRATION"),
                TurnEvent(old_token, "image_generated", "STALE.png"),
            ]:
                workers.llm_worker.turn_event.emit(event)
            app.processEvents()
            assert window.message_history_snapshot() == before
            assert window._waiting_for_reply and played == []

            second_id = chat_history.get_active_session_id()
            window.session_switch_requested.emit(old_id)
            pump(app, lambda: workers.llm_worker._active_token is None)
            assert visible("switch:first") and not visible("current:first")
            window.session_switch_requested.emit(second_id)
            assert visible("current:first") and not visible("switch:first")

            # Closing with simultaneous LLM, TTS and CG work must keep Qt alive until all stop.
            window.stop_btn.click()
            pump(app, lambda: workers.llm_worker._active_token is None)
            tts = WaitingMedia()
            setup.runtime.tts_manager = tts
            adapter.mode = "closing"
            send("closing")
            pump(app, lambda: tts.started.is_set())
            setup.t2i_prompt_queue.put(TurnWork(controller.token, "test image"))
            pump(app, lambda: cg.started.is_set())
            if len(sys.argv) > 1:
                window.grab().save(sys.argv[1])
            started = time.monotonic()
            window.close()
            pump(app, lambda: not window.isVisible() and all(not w.isRunning() for _, w in workers._iter_workers()))
            assert tts.cleaned.is_set() and cg.cleaned.is_set()
            assert time.monotonic() - started < 3
            print("PASS: real Qt streaming, stop, new session, stale events, and active LLM/TTS/CG shutdown")
        finally:
            controller.cancel(notify=False)
            workers.stop_all()
            window.close()
            window.deleteLater()
            clear_app_runtime()


if __name__ == "__main__":
    main()
