from queue import Queue
import sys
import types

pyside6_module = types.ModuleType("PySide6")
qtcore_module = types.ModuleType("PySide6.QtCore")


class _SignalInstance:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback, *connection_type):
        self._callbacks.append(callback)

    def emit(self, *args, **kwargs):
        for callback in list(self._callbacks):
            callback(*args, **kwargs)


class _SignalDescriptor:
    def __set_name__(self, owner, name):
        self._storage_name = f"__signal_{name}"

    def __get__(self, instance, owner):
        if instance is None:
            return self
        signal = instance.__dict__.get(self._storage_name)
        if signal is None:
            signal = _SignalInstance()
            instance.__dict__[self._storage_name] = signal
        return signal


class Signal:
    def __new__(cls, *args, **kwargs):
        return _SignalDescriptor()


class QThread:
    def __init__(self, *args, **kwargs):
        pass


qtcore_module.QThread = QThread
qtcore_module.Signal = Signal
pyside6_module.QtCore = qtcore_module
_ORIGINAL_PYSIDE6 = {
    name: sys.modules.get(name)
    for name in (
        "PySide6",
        "PySide6.QtCore",
    )
}

sys.modules["PySide6"] = pyside6_module
sys.modules["PySide6.QtCore"] = qtcore_module

from core.runtime.app_runtime import AppRuntime, set_app_runtime
from core.runtime.workers import LLMWorker

for _name, _module in _ORIGINAL_PYSIDE6.items():
    if _module is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _module

from core.runtime.tool_summary import ToolInvocationRecord, ToolLoopTurnResult, ToolTurnSummary


class FakeConfig:
    characters = [type("Character", (), {"name": "诺艾尔"})()]


class FakeCompactManager:
    def __init__(self, *args, **kwargs):
        pass

    def auto_compact(self, messages, adapter):
        return messages

    def build_context(self, messages, **kwargs):
        return list(messages)


class FakeLLMManager:
    max_tokens = 128000

    def __init__(self):
        self.adapter = object()
        self._messages = [{"role": "system", "content": "system"}]

    def get_messages(self):
        return list(self._messages)

    def set_messages(self, messages):
        self._messages = list(messages)

    def build_user_message(self, text):
        return {"role": "user", "content": text}

    def get_generation_config(self):
        return {"max_tokens": 4096}


class RecordingToolManager:
    def register(self, *args, **kwargs):
        return None

    def get_tool_definitions(self):
        return []


class StubRuntimeResult(ToolLoopTurnResult):
    pass


def _install_runtime(llm_manager, tool_manager=None, user_input_queue=None, tts_queue=None):
    user_input_queue = user_input_queue or Queue()
    tts_queue = tts_queue or Queue()
    runtime = AppRuntime(
        config=FakeConfig(),
        llm_manager=llm_manager,
        tts_manager=None,
        user_input_queue=user_input_queue,
        tts_queue=tts_queue,
        audio_path_queue=Queue(),
    )
    runtime.tool_manager = tool_manager
    set_app_runtime(runtime)
    return user_input_queue, tts_queue


def test_llm_worker_delegates_turn_to_runtime_and_emits_dialog(monkeypatch):
    import llm.compact_manager
    import core.runtime.llm_worker as llm_worker_module

    monkeypatch.setattr(llm.compact_manager, "CompactManager", FakeCompactManager)

    calls = []
    llm_manager = FakeLLMManager()
    tool_manager = RecordingToolManager()
    user_input_queue, tts_queue = _install_runtime(llm_manager, tool_manager)
    worker = LLMWorker(user_input_queue, tts_queue)
    parsed = []
    statuses = []
    ended = []
    worker.dialog_parsed.connect(lambda msg: parsed.append(msg))
    worker.status_changed.connect(lambda text: statuses.append(text))
    worker.stream_end.connect(lambda: ended.append(True))

    runtime_result = StubRuntimeResult(
        final_output="收到，我在这里。",
        invocation_records=[],
        summary=ToolTurnSummary(total_count=0, success_count=0, failure_count=0),
        updated_messages=[
            {"role": "system", "content": "system"},
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "收到，我在这里。"},
        ],
    )

    def fake_run_user_turn(*, llm_manager, tool_manager, user_text, max_loops=6, progress_callback=None):
        calls.append(
            {
                "llm_manager": llm_manager,
                "tool_manager": tool_manager,
                "user_text": user_text,
                "max_loops": max_loops,
            }
        )
        return runtime_result

    monkeypatch.setattr(llm_worker_module, "run_user_turn", fake_run_user_turn)

    worker._handle_user_text_once("你好")

    assert calls[0]["llm_manager"] is not llm_manager
    assert calls[0]["llm_manager"].get_messages() == llm_manager.get_messages()
    assert calls == [
        {
            "llm_manager": calls[0]["llm_manager"],
            "tool_manager": tool_manager,
            "user_text": "你好",
            "max_loops": 6,
        }
    ]
    assert len(parsed) == 1
    assert parsed[0].name == "诺艾尔"
    assert parsed[0].text == "收到，我在这里。"
    assert tts_queue.get_nowait().text == "收到，我在这里。"
    assert "模型思考中..." in statuses
    assert statuses[-1] == ""
    assert ended == [True]


def test_llm_worker_emits_structured_tool_summary_signal(monkeypatch):
    import llm.compact_manager
    import core.runtime.llm_worker as llm_worker_module

    monkeypatch.setattr(llm.compact_manager, "CompactManager", FakeCompactManager)

    llm_manager = FakeLLMManager()
    tool_manager = RecordingToolManager()
    user_input_queue, tts_queue = _install_runtime(llm_manager, tool_manager)
    worker = LLMWorker(user_input_queue, tts_queue)
    parsed = []
    tool_summaries = []
    worker.dialog_parsed.connect(lambda msg: parsed.append(msg))
    worker.tool_summary_ready.connect(lambda payload: tool_summaries.append(payload))

    records = [
        ToolInvocationRecord(
            order_index=0,
            tool_name="echo_tool",
            status="success",
            arguments_summary='{"text": "hello"}',
            result_summary='{"echo": "hello"}',
        )
    ]
    runtime_result = StubRuntimeResult(
        final_output='{"character_name": "诺艾尔", "speech": "工具执行完毕。", "sprite": "0"}',
        invocation_records=records,
        summary=ToolTurnSummary.from_records(records),
        updated_messages=[
            {"role": "system", "content": "system"},
            {"role": "user", "content": "调用工具"},
            {"role": "assistant", "content": "工具执行完毕。"},
        ],
    )

    monkeypatch.setattr(
        llm_worker_module,
        "run_user_turn",
        lambda **kwargs: runtime_result,
    )

    worker._handle_user_text_once("调用工具")

    assert len(parsed) == 1
    assert parsed[0].name == "诺艾尔"
    assert parsed[0].text == "工具执行完毕。"
    assert tts_queue.get_nowait().text == "工具执行完毕。"
    assert len(tool_summaries) == 1
    assert tool_summaries[0].summary.total_count == 1
    assert tool_summaries[0].summary.success_count == 1
    assert tool_summaries[0].invocation_records[0].tool_name == "echo_tool"
