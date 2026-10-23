from queue import Queue

import pytest

from core.runtime.app_runtime import (
    AppRuntime,
    clear_app_runtime,
    get_app_runtime,
    set_app_runtime,
    try_get_app_runtime,
)
from core.runtime.runtime_setup import RuntimeSetup, create_runtime_setup


class FakeConfig:
    pass


class FakeLLMManager:
    pass


class FakeTTSManager:
    pass


def test_create_runtime_setup_creates_four_distinct_queues_and_returns_runtime_setup(monkeypatch):
    monkeypatch.setattr("core.runtime.app_runtime._app_runtime", None)

    setup = create_runtime_setup(FakeConfig(), FakeLLMManager(), FakeTTSManager())

    assert isinstance(setup, RuntimeSetup)
    assert isinstance(setup.user_input_queue, Queue)
    assert isinstance(setup.tts_queue, Queue)
    assert isinstance(setup.audio_path_queue, Queue)
    assert isinstance(setup.t2i_prompt_queue, Queue)
    assert setup.user_input_queue is not setup.tts_queue
    assert setup.user_input_queue is not setup.audio_path_queue
    assert setup.user_input_queue is not setup.t2i_prompt_queue
    assert setup.tts_queue is not setup.audio_path_queue
    assert setup.tts_queue is not setup.t2i_prompt_queue
    assert setup.audio_path_queue is not setup.t2i_prompt_queue


def test_create_runtime_setup_binds_runtime_fields_and_sets_global_runtime(monkeypatch):
    monkeypatch.setattr("core.runtime.app_runtime._app_runtime", None)
    config = FakeConfig()
    llm_manager = FakeLLMManager()
    tts_manager = FakeTTSManager()

    setup = create_runtime_setup(config, llm_manager, tts_manager)

    assert setup.runtime.config is config
    assert setup.runtime.llm_manager is llm_manager
    assert setup.runtime.tts_manager is tts_manager
    assert setup.runtime.user_input_queue is setup.user_input_queue
    assert setup.runtime.tts_queue is setup.tts_queue
    assert setup.runtime.audio_path_queue is setup.audio_path_queue
    assert get_app_runtime() is setup.runtime


def test_create_runtime_setup_includes_t2i_prompt_queue(monkeypatch):
    from core.runtime import runtime_setup as runtime_setup_module

    captured = {}

    def fake_set_app_runtime(runtime):
        captured["runtime"] = runtime

    monkeypatch.setattr(runtime_setup_module, "set_app_runtime", fake_set_app_runtime)

    setup = runtime_setup_module.create_runtime_setup(object(), object(), object())

    assert setup.t2i_prompt_queue is not None
    assert isinstance(setup.t2i_prompt_queue, Queue)
    assert captured["runtime"].user_input_queue is setup.user_input_queue
    assert captured["runtime"].tts_queue is setup.tts_queue
    assert captured["runtime"].audio_path_queue is setup.audio_path_queue


def test_clear_app_runtime_clears_registered_runtime(monkeypatch):
    monkeypatch.setattr("core.runtime.app_runtime._app_runtime", None)
    runtime = AppRuntime(
        config=FakeConfig(),
        llm_manager=FakeLLMManager(),
        tts_manager=FakeTTSManager(),
    )
    set_app_runtime(runtime)

    clear_app_runtime()

    assert try_get_app_runtime() is None
    with pytest.raises(RuntimeError, match="AppRuntime 尚未初始化"):
        get_app_runtime()


def test_clear_app_runtime_is_idempotent(monkeypatch):
    monkeypatch.setattr("core.runtime.app_runtime._app_runtime", None)

    clear_app_runtime()
    clear_app_runtime()

    assert try_get_app_runtime() is None
