import json
from queue import Queue

import pytest

from core.runtime.app_runtime import AppRuntime, set_app_runtime
from core.sprite import chat_history


class FakeLLMManager:
    def __init__(self, messages):
        self._messages = messages

    def get_messages(self):
        return list(self._messages)

    def set_messages(self, messages):
        self._messages = list(messages)

    def clear_history(self):
        self._messages = [m for m in self._messages if m.get("role") == "system"]


@pytest.fixture(autouse=True)
def isolate_chat_history_default_file(tmp_path, monkeypatch):
    """避免测试读写真实 data/chat_history/default.json，并隔离内存 UI 历史。"""
    monkeypatch.setattr(chat_history, "DEFAULT_FILE", tmp_path / "default.json")
    monkeypatch.setattr(chat_history, "HISTORY_DIR", tmp_path)
    monkeypatch.setattr(chat_history, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(chat_history, "SESSIONS_INDEX_FILE", tmp_path / "sessions.json")
    chat_history.set_session_store(
        chat_history.SessionStore(
            history_root=tmp_path,
            sessions_dir=tmp_path / "sessions",
            index_path=tmp_path / "sessions.json",
            legacy_default_file=tmp_path / "default.json",
        )
    )
    chat_history.ensure_default_session(title="默认会话", character_name="诺艾尔")
    active_session_id = chat_history.get_active_session_id()
    if active_session_id:
        chat_history.load_session(active_session_id)
    chat_history.chat_history.clear()
    yield
    chat_history.chat_history.clear()


def test_load_preserves_current_system_prompt_when_history_has_no_system(tmp_path):
    llm = FakeLLMManager([
        {"role": "system", "content": "CURRENT_SYSTEM_PROMPT"},
    ])
    set_app_runtime(AppRuntime(config=None, llm_manager=llm, tts_manager=None,
                               user_input_queue=Queue(), tts_queue=Queue(), audio_path_queue=Queue()))
    history_file = tmp_path / "history.json"
    history_file.write_text(json.dumps({
        "messages": [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "普通文本旧回复"},
        ],
        "ui_history": [],
    }, ensure_ascii=False), encoding="utf-8")

    assert chat_history.load(str(history_file)) is True

    assert llm.get_messages()[0] == {"role": "system", "content": "CURRENT_SYSTEM_PROMPT"}
    assert [m["role"] for m in llm.get_messages()] == ["system", "user", "assistant"]


def test_load_replaces_stale_history_system_prompt_with_current_system_prompt(tmp_path):
    llm = FakeLLMManager([
        {"role": "system", "content": "CURRENT_SYSTEM_PROMPT"},
    ])
    set_app_runtime(AppRuntime(config=None, llm_manager=llm, tts_manager=None,
                               user_input_queue=Queue(), tts_queue=Queue(), audio_path_queue=Queue()))
    history_file = tmp_path / "history.json"
    history_file.write_text(json.dumps({
        "messages": [
            {"role": "system", "content": "STALE_SYSTEM_PROMPT"},
            {"role": "user", "content": "你好"},
        ],
        "ui_history": [],
    }, ensure_ascii=False), encoding="utf-8")

    assert chat_history.load(str(history_file)) is True

    assert llm.get_messages()[0] == {"role": "system", "content": "CURRENT_SYSTEM_PROMPT"}
    assert "STALE_SYSTEM_PROMPT" not in [m["content"] for m in llm.get_messages()]


def test_clear_history_clears_ui_history_and_preserves_llm_system_prompt():
    llm = FakeLLMManager([
        {"role": "system", "content": "CURRENT_SYSTEM_PROMPT"},
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "普通文本回复"},
    ])
    set_app_runtime(AppRuntime(config=None, llm_manager=llm, tts_manager=None,
                               user_input_queue=Queue(), tts_queue=Queue(), audio_path_queue=Queue()))
    chat_history.chat_history.clear()
    chat_history.add_to_history("user", "你好")
    chat_history.add_to_history("assistant", "普通文本回复", name="诺艾尔")

    chat_history.clear_history()

    assert chat_history.get_history() == []
    assert llm.get_messages() == [{"role": "system", "content": "CURRENT_SYSTEM_PROMPT"}]


def test_get_last_user_content_returns_latest_user_entry():
    chat_history.chat_history.clear()
    chat_history.add_to_history("user", "第一句")
    chat_history.add_to_history("assistant", "回复")
    chat_history.add_to_history("user", "请再说一次")

    assert chat_history.get_last_user_content() == "请再说一次"


def test_get_last_user_content_returns_none_without_user_entry():
    chat_history.add_to_history("assistant", "只有回复")

    assert chat_history.get_last_user_content() is None


@pytest.mark.parametrize("entry", [
    {"role": "user"},
    {"role": "user", "content": None},
    {"role": "user", "content": 123},
    {"role": "user", "content": ""},
    {"role": "user", "content": " \t\n"},
])
def test_get_last_user_content_returns_none_for_missing_or_invalid_content(entry):
    chat_history.chat_history.append(entry)

    assert chat_history.get_last_user_content() is None


def test_get_last_user_content_skips_invalid_latest_user_and_returns_latest_valid_user():
    chat_history.add_to_history("user", "第一句")
    chat_history.add_to_history("assistant", "回复")
    chat_history.chat_history.append({"role": "user", "content": "   "})

    assert chat_history.get_last_user_content() == "第一句"


def test_pop_last_turn_removes_only_last_turn_and_keeps_earlier_history():
    llm = FakeLLMManager([
        {"role": "system", "content": "CURRENT_SYSTEM_PROMPT"},
        {"role": "user", "content": "第一句"},
        {"role": "assistant", "content": "第一句回复"},
        {"role": "user", "content": "第二句"},
        {"role": "assistant", "content": "第二句回复"},
    ])
    set_app_runtime(AppRuntime(config=None, llm_manager=llm, tts_manager=None,
                               user_input_queue=Queue(), tts_queue=Queue(), audio_path_queue=Queue()))
    chat_history.chat_history.clear()
    chat_history.add_to_history("user", "第一句")
    chat_history.add_to_history("assistant", "第一句回复", name="诺艾尔")
    chat_history.add_to_history("system", "中间系统提示", name="系统")
    chat_history.add_to_history("user", "第二句")
    chat_history.add_to_history("assistant", "第二句回复", name="诺艾尔")

    assert chat_history.pop_last_turn() is True

    assert llm.get_messages() == [
        {"role": "system", "content": "CURRENT_SYSTEM_PROMPT"},
        {"role": "user", "content": "第一句"},
        {"role": "assistant", "content": "第一句回复"},
    ]
    assert chat_history.get_history() == [
        {"role": "user", "content": "第一句"},
        {"role": "assistant", "content": "第一句回复", "name": "诺艾尔"},
        {"role": "system", "content": "中间系统提示", "name": "系统"},
    ]


def test_pop_last_turn_without_last_assistant_keeps_earlier_completed_turn():
    llm = FakeLLMManager([
        {"role": "system", "content": "CURRENT_SYSTEM_PROMPT"},
        {"role": "user", "content": "第一句"},
        {"role": "assistant", "content": "第一句回复"},
        {"role": "user", "content": "第二句"},
    ])
    set_app_runtime(AppRuntime(config=None, llm_manager=llm, tts_manager=None,
                               user_input_queue=Queue(), tts_queue=Queue(), audio_path_queue=Queue()))
    chat_history.chat_history.clear()
    chat_history.add_to_history("user", "第一句")
    chat_history.add_to_history("assistant", "第一句回复", name="诺艾尔")
    chat_history.add_to_history("user", "第二句")

    assert chat_history.pop_last_turn() is True

    assert llm.get_messages() == [
        {"role": "system", "content": "CURRENT_SYSTEM_PROMPT"},
        {"role": "user", "content": "第一句"},
        {"role": "assistant", "content": "第一句回复"},
    ]
    assert chat_history.get_history() == [
        {"role": "user", "content": "第一句"},
        {"role": "assistant", "content": "第一句回复", "name": "诺艾尔"},
    ]


def test_pop_last_turn_returns_false_and_does_not_save_when_ui_history_has_no_user():
    llm = FakeLLMManager([
        {"role": "system", "content": "CURRENT_SYSTEM_PROMPT"},
        {"role": "user", "content": "只有 LLM 有 user"},
        {"role": "assistant", "content": "回复"},
    ])
    set_app_runtime(AppRuntime(config=None, llm_manager=llm, tts_manager=None,
                               user_input_queue=Queue(), tts_queue=Queue(), audio_path_queue=Queue()))
    chat_history.add_to_history("assistant", "UI 只有回复", name="诺艾尔")

    assert chat_history.pop_last_turn() is False

    assert llm.get_messages() == [
        {"role": "system", "content": "CURRENT_SYSTEM_PROMPT"},
        {"role": "user", "content": "只有 LLM 有 user"},
        {"role": "assistant", "content": "回复"},
    ]
    assert chat_history.get_history() == [
        {"role": "assistant", "content": "UI 只有回复", "name": "诺艾尔"},
    ]


def test_create_and_switch_sessions_keep_histories_isolated():
    llm = FakeLLMManager([
        {"role": "system", "content": "CURRENT_SYSTEM_PROMPT"},
    ])
    set_app_runtime(AppRuntime(config=None, llm_manager=llm, tts_manager=None,
                               user_input_queue=Queue(), tts_queue=Queue(), audio_path_queue=Queue()))

    chat_history.add_to_history("user", "默认会话内容")
    chat_history.save()
    first_session_id = chat_history.get_active_session_id()

    second = chat_history.create_session(title="第二会话", character_name="诺艾尔", make_active=True)
    chat_history.add_to_history("user", "第二会话内容")
    chat_history.save()

    assert chat_history.switch_session(first_session_id) is True
    assert chat_history.get_history() == [{"role": "user", "content": "默认会话内容"}]

    assert chat_history.switch_session(second.id) is True
    assert chat_history.get_history() == [{"role": "user", "content": "第二会话内容"}]
