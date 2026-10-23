import json
from queue import Queue
from types import SimpleNamespace

from core.runtime.app_runtime import AppRuntime
from core.runtime.cancellation import TurnEvent, TurnToken, TurnWork
from core.runtime.llm_worker import LLMWorker
from llm.llm_manager import LLMManager
from llm.tools.tool_manager import ToolManager


def test_worker_emits_complete_dialog_before_stream_finishes_and_commits_no_shared_history(monkeypatch):
    events = []
    first = json.dumps({"character_name": "Test", "speech": "第一句", "sprite": "1"}, ensure_ascii=False)
    second = json.dumps({"character_name": "Test", "speech": "第二句", "sprite": "2"}, ensure_ascii=False)

    class Adapter:
        def generate_stream(self, messages, *, tools, generation_config, on_text):
            on_text(first[:20])
            assert not any(e.kind == "dialog_parsed" for e in events)
            on_text(first[20:])
            assert [e.payload.text for e in events if e.kind == "dialog_parsed"] == ["第一句"]
            on_text("\n" + second)
            return {"content": first + "\n" + second, "tool_calls": []}

    manager = LLMManager(Adapter(), user_template="JSON")
    runtime = AppRuntime(config=SimpleNamespace(characters=[]), llm_manager=manager)
    runtime.tool_manager = ToolManager()
    monkeypatch.setattr("core.runtime.app_runtime._app_runtime", runtime)
    token = TurnToken("session-a")
    worker = LLMWorker(Queue(), runtime.tts_queue)
    worker.turn_event.connect(events.append)
    worker._handle_user_text_once(TurnWork(token, ("hello", manager.get_messages())))
    assert [e.payload.text for e in events if e.kind == "dialog_parsed"] == ["第一句", "第二句"]
    assert all(isinstance(e, TurnEvent) and e.token is token for e in events)
    assert runtime.tts_queue.qsize() == 2
    assert runtime.tts_queue.get_nowait().token is token
    assert manager.get_messages() == [{"role": "system", "content": "JSON"}]
    result = next(e.payload for e in events if e.kind == "tool_summary_ready")
    assert result.updated_messages[-1]["content"] == first + "\n" + second


def test_cancelled_queued_turn_never_calls_model(monkeypatch):
    class Adapter:
        def generate_stream(self, *args, **kwargs):
            raise AssertionError("cancelled queued turn reached the model")

    manager = LLMManager(Adapter())
    runtime = AppRuntime(config=SimpleNamespace(characters=[]), llm_manager=manager)
    runtime.tool_manager = ToolManager()
    monkeypatch.setattr("core.runtime.app_runtime._app_runtime", runtime)
    token = TurnToken()
    token.cancel()
    events = []
    worker = LLMWorker(Queue(), Queue())
    worker.turn_event.connect(events.append)
    worker._handle_user_text_once(TurnWork(token, ("hello", [])))
    assert events == []
