"""Offline end-to-end memory check with real Qt, workers, UI and temporary storage."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase
from config.schema import Character
from core.runtime.app_runtime import clear_app_runtime
from core.runtime.runtime_setup import create_runtime_setup
from core.runtime.worker_lifecycle import create_runtime_workers
from core.runtime.signal_wiring import wire_runtime_signals
from core.sessions.store import SessionStore
from core.sprite import chat_history
from llm.llm_manager import LLMManager
from llm.tools.tool_manager import ToolManager
from ui.chat_ui.chat_ui import ChatUIWindow
from ui.settings_ui.memory_tab import MemoryTab


def pump(app, predicate, timeout=6):
    deadline = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        if time.monotonic() > deadline:
            raise AssertionError("Timed out waiting for memory/UI state")
        time.sleep(0.005)
    app.processEvents()


class Adapter:
    def __init__(self):
        self.requests = []

    def generate_stream(self, messages, *, tools, generation_config, on_text):
        if generation_config.get("_plain_text"):
            data = json.loads(messages[-1]["content"])
            return {"content": json.dumps({"summary": "约好下次去书店。", "memories": [{
                "type": "promise", "topic": "去书店的约定", "content": "下次一起去书店", "evidence": "下次一起去书店",
                "source_turn_ids": [data["valid_turn_ids"][0]], "certainty": "explicit", "importance": 4,
            }]}, ensure_ascii=False)}
        self.requests.append(messages)
        text = json.dumps({"character_name": "爱丽丝", "speech": "好呀，我会记得。", "sprite": "-1"}, ensure_ascii=False)
        on_text(text)
        return {"content": text, "tool_calls": []}


def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    font = Path("C:/Windows/Fonts/msyh.ttc")
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
        app.setFont(QFont("Microsoft YaHei", 10))
    with tempfile.TemporaryDirectory(prefix="galgame-memory-smoke-") as directory:
        root = Path(directory)
        sessions = SessionStore(history_root=root, sessions_dir=root / "sessions", index_path=root / "sessions.json",
                                legacy_default_file=root / "default.json")
        chat_history.set_session_store(sessions)
        character = Character(name="爱丽丝")
        config = NS(characters=[character], backgrounds=[], default_skills=[], skill_presets=[])
        adapter = Adapter()
        manager = LLMManager(adapter, user_template="Reply in JSON")
        setup = create_runtime_setup(config, manager, None)
        setup.runtime.tool_manager = ToolManager()
        original = chat_history.ensure_default_session(character_name=character.name)
        chat_history.load_session(original.id)
        workers = create_runtime_workers(setup)
        window = ChatUIWindow()
        handles = wire_runtime_signals(window=window, workers=workers, runtime_setup=setup, config=config,
            llm_context=NS(active_character_name=character.name, active_character_color="#ABCDEF"),
            chat_history=chat_history, sprite_controller=NS(set_sprite_by_id=lambda _: None),
            audio_player=NS(play=lambda _: None, stop=lambda: None))
        controller = handles.turn_controller
        tab = MemoryTab(config, history=chat_history)
        workers.start_all()
        window.show()

        def send(text):
            window.input_edit.setText(text)
            window.send_btn.click()
            pump(app, lambda: not window._waiting_for_reply)

        try:
            send("请记住，下次一起去书店")
            pump(app, lambda: sessions.memory.session(original.id)["status"] == "ready")
            memories = sessions.memory.list_memories(original.id)
            assert len(memories) == 1 and memories[0]["status"] == "active"
            assert memories[0]["source_turn_ids"] == [controller.token.id]
            send("我们下次做什么？")
            assert any("相关记忆" in m.get("content", "") and "书店" in m["content"] for m in adapter.requests[-1])
            assert len(manager.get_messages()) == 5
            assert not any("相关记忆" in m.get("content", "") for m in manager.get_messages())
            # Durable logs reload without injecting fake user turns.
            before = manager.get_messages()
            assert chat_history.load_session(original.id)
            assert manager.get_messages() == before
            tab.resize(1150, 900)
            tab.show()
            app.processEvents()
            assert tab.list.count() == 1 and "下次一起去书店" in tab.source_text.toPlainText()
            tab.content.setPlainText("下次先去花店，再去书店")
            tab.pinned.setChecked(True)
            tab.save_memory()
            send("我们的约定？")
            assert any("先去花店" in m.get("content", "") for m in adapter.requests[-1])
            if len(sys.argv) > 1:
                tab.grab().save(sys.argv[1])
            # Fresh sessions cannot access the old promise.
            window.new_session_requested.emit("全局默认")
            fresh_id = chat_history.get_active_session_id()
            assert fresh_id != original.id
            send("书店")
            assert not any("相关记忆" in m.get("content", "") for m in adapter.requests[-1])
            window.session_switch_requested.emit(original.id)
            controller.cancel(notify=False)
            assert chat_history.revert_to(0)
            assert sessions.memory.retrieve(original.id, "书店") == []
            assert sessions.memory.summaries(original.id) == []
            print("PASS: Qt send -> background extract -> recall -> durable reload -> edit/pin -> isolation -> rewind")
        finally:
            tab.close()
            controller.shutdown()
            workers.stop_all()
            window.close()
            window.deleteLater()
            tab.deleteLater()
            app.processEvents()
            clear_app_runtime()


if __name__ == "__main__":
    main()
