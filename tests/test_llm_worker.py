from queue import Queue
from types import SimpleNamespace

import pytest

from core.runtime.app_runtime import AppRuntime, set_app_runtime
from core.runtime.workers import LLMWorker
from llm.tools.tool_manager import ToolManager


class FakeAdapter:
    def __init__(self, response=None):
        self.response = response or [{"role": "assistant", "content": "你好！很高兴见到你。"}]

    def generate(self, messages, *, tools=None, generation_config=None):
        item = self.response[0]
        if isinstance(item, str):
            return {"role": "assistant", "content": item}
        return item


class FakeLLMManager:
    max_tokens = 128000

    def __init__(self, response=None):
        self.adapter = FakeAdapter(response)
        self._messages = [{"role": "system", "content": "system"}]

    def get_messages(self):
        return list(self._messages)

    def set_messages(self, messages):
        self._messages = list(messages)

    def get_generation_config(self):
        return {}

    def build_user_message(self, user_text):
        return {"role": "user", "content": f"用户：\n{user_text}"}


class FakeConfig:
    characters = [type("Character", (), {"name": "诺艾尔"})()]


class FakeCompactManager:
    def __init__(self, *args, **kwargs):
        pass

    def auto_compact(self, messages, adapter):
        return messages

    def build_context(self, messages, **kwargs):
        return list(messages)

    def fit_request(self, messages, **kwargs):
        return list(messages)


def _install_runtime(llm, user_input_queue=None, tts_queue=None, *, config=None):
    user_input_queue = user_input_queue or Queue()
    tts_queue = tts_queue or Queue()
    runtime = AppRuntime(config=FakeConfig() if config is None else config, llm_manager=llm, tts_manager=None,
                         user_input_queue=user_input_queue, tts_queue=tts_queue,
                         audio_path_queue=Queue())
    runtime.tool_manager = ToolManager()
    set_app_runtime(runtime)
    return user_input_queue, tts_queue


def test_llm_worker_emits_fallback_dialog_when_response_is_plain_text(monkeypatch):
    import llm.compact_manager

    monkeypatch.setattr(llm.compact_manager, "CompactManager", FakeCompactManager)
    user_input_queue = Queue()
    tts_queue = Queue()
    llm = FakeLLMManager()
    _install_runtime(llm, user_input_queue, tts_queue)
    worker = LLMWorker(user_input_queue, tts_queue)
    parsed = []
    ended = []
    worker.dialog_parsed.connect(lambda msg: parsed.append(msg))
    worker.stream_end.connect(lambda: ended.append(True))

    worker._handle_user_text_once("你好")

    assert len(parsed) == 1
    assert parsed[0].name == "诺艾尔"
    assert parsed[0].text == "你好！很高兴见到你。"
    assert tts_queue.get_nowait().text == "你好！很高兴见到你。"
    assert ended == [True]


def test_llm_worker_emits_safe_fallback_dialog_when_json_is_invalid(monkeypatch):
    import llm.compact_manager

    monkeypatch.setattr(llm.compact_manager, "CompactManager", FakeCompactManager)
    raw = ['{"bad": "value", "api_key": "sk-secret", "sprite": "0"}']
    user_input_queue = Queue()
    tts_queue = Queue()
    llm = FakeLLMManager(response=raw)
    _install_runtime(llm, user_input_queue, tts_queue)
    worker = LLMWorker(user_input_queue, tts_queue)
    parsed = []
    worker.dialog_parsed.connect(lambda msg: parsed.append(msg))

    worker._handle_user_text_once("你好")

    assert len(parsed) == 1
    assert parsed[0].name == "诺艾尔"
    assert parsed[0].asset_id == "-1"
    assert "格式异常" in parsed[0].text or "检查角色模板" in parsed[0].text
    assert "character_name" not in parsed[0].text
    assert "sprite" not in parsed[0].text
    assert "api_key" not in parsed[0].text
    assert "sk-secret" not in parsed[0].text
    queued = tts_queue.get_nowait()
    assert queued.text == parsed[0].text


@pytest.mark.parametrize("response", [
    "这是当前角色的普通文字回复。",
    '{"bad": "value", "api_key": "sk-secret", "sprite": "0"}',
])
def test_llm_worker_fallback_uses_selected_character_instead_of_first(monkeypatch, response):
    import llm.compact_manager

    monkeypatch.setattr(llm.compact_manager, "CompactManager", FakeCompactManager)
    config = SimpleNamespace(
        characters=[SimpleNamespace(memory_id="first", name="第一个角色"),
                    SimpleNamespace(memory_id="selected", name="选中的角色")],
        system_config=SimpleNamespace(active_character_id="selected"),
    )
    llm = FakeLLMManager(response=[response])
    user_queue, tts_queue = _install_runtime(llm, config=config)
    worker = LLMWorker(user_queue, tts_queue)
    parsed = []
    worker.dialog_parsed.connect(parsed.append)

    worker._handle_user_text_once("你好")

    assert len(parsed) == 1
    assert parsed[0].name == "选中的角色"
    assert tts_queue.get_nowait().name == "选中的角色"
    assert "sk-secret" not in parsed[0].text


def test_llm_worker_emits_dialog_for_json_response(monkeypatch):
    import llm.compact_manager
    monkeypatch.setattr(llm.compact_manager, "CompactManager", FakeCompactManager)

    raw = ['{"character_name": "诺艾尔", "speech": "收到，我在这里。", "sprite": "0"}']
    user_input_queue = Queue()
    tts_queue = Queue()
    llm = FakeLLMManager(response=raw)
    _install_runtime(llm, user_input_queue, tts_queue)
    worker = LLMWorker(user_input_queue, tts_queue)
    parsed = []
    worker.dialog_parsed.connect(lambda msg: parsed.append(msg))

    worker._handle_user_text_once("你好")

    assert len(parsed) == 1
    assert parsed[0].name == "诺艾尔"
    assert parsed[0].text == "收到，我在这里。"
    assert tts_queue.get_nowait().text == "收到，我在这里。"


def test_llm_worker_emits_multiple_dialogs_for_multi_json_response(monkeypatch):
    import llm.compact_manager
    monkeypatch.setattr(llm.compact_manager, "CompactManager", FakeCompactManager)

    raw = [
        '{"character_name": "NARR", "speech": "风吹过窗边。", "sprite": "-1"}\n'
        '{"character_name": "诺艾尔", "speech": "我听见了。", "sprite": "1"}'
    ]
    user_input_queue = Queue()
    tts_queue = Queue()
    llm = FakeLLMManager(response=raw)
    _install_runtime(llm, user_input_queue, tts_queue)
    worker = LLMWorker(user_input_queue, tts_queue)
    parsed = []
    worker.dialog_parsed.connect(lambda msg: parsed.append(msg))

    worker._handle_user_text_once("继续")

    assert [m.name for m in parsed] == ["NARR", "诺艾尔"]
    assert [tts_queue.get_nowait().name, tts_queue.get_nowait().name] == ["NARR", "诺艾尔"]


def test_llm_worker_emits_status_lifecycle(monkeypatch):
    import llm.compact_manager
    monkeypatch.setattr(llm.compact_manager, "CompactManager", FakeCompactManager)

    user_input_queue = Queue()
    tts_queue = Queue()
    llm = FakeLLMManager(response=['{"character_name": "诺艾尔", "speech": "好了。", "sprite": "0"}'])
    _install_runtime(llm, user_input_queue, tts_queue)
    worker = LLMWorker(user_input_queue, tts_queue)
    statuses = []
    worker.status_changed.connect(lambda text: statuses.append(text))

    worker._handle_user_text_once("测试")

    assert "模型思考中..." in statuses
    assert "正在回复..." in statuses
    assert statuses[-1] == ""
