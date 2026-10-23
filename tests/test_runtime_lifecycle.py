from types import SimpleNamespace

import pytest

from core.runtime import runtime_lifecycle
from core.runtime.runtime_lifecycle import run_runtime_event_loop


class FakeRuntimeEventLoopWorkers:
    def __init__(self, calls, *, start_error=None, stop_error=None):
        self.calls = calls
        self.start_error = start_error
        self.stop_error = stop_error

    def start_all(self):
        self.calls.append("workers.start_all")
        if self.start_error is not None:
            raise self.start_error

    def stop_all(self):
        self.calls.append("workers.stop_all")
        if self.stop_error is not None:
            raise self.stop_error


class FakeRuntimeEventLoopWindow:
    def __init__(self, calls):
        self.calls = calls

    def show(self):
        self.calls.append("window.show")


class FakeRuntimeEventLoopSpriteController:
    def __init__(self, calls):
        self.calls = calls

    def show_default_sprite(self):
        self.calls.append("sprite_controller.show_default_sprite")


class FakeRuntimeEventLoopApp:
    def __init__(self, calls, *, exec_result=7, exec_error=None):
        self.calls = calls
        self.exec_result = exec_result
        self.exec_error = exec_error

    def exec(self):
        self.calls.append("app.exec")
        if self.exec_error is not None:
            raise self.exec_error
        return self.exec_result


class FakeRuntimeEventLoopChatHistory:
    def __init__(self, calls, *, save_error=None):
        self.calls = calls
        self.save_error = save_error

    def save(self):
        self.calls.append("chat_history.save")
        if self.save_error is not None:
            raise self.save_error


def make_runtime_event_loop_handles(
    *,
    start_error=None,
    exec_error=None,
    stop_error=None,
    save_error=None,
    mcp_controller=None,
):
    calls = []
    return SimpleNamespace(
        calls=calls,
        workers=FakeRuntimeEventLoopWorkers(
            calls,
            start_error=start_error,
            stop_error=stop_error,
        ),
        window=FakeRuntimeEventLoopWindow(calls),
        sprite_controller=FakeRuntimeEventLoopSpriteController(calls),
        app=FakeRuntimeEventLoopApp(calls, exec_error=exec_error),
        chat_history=FakeRuntimeEventLoopChatHistory(calls, save_error=save_error),
        mcp_controller=mcp_controller,
    )


@pytest.fixture
def runtime_event_loop_clear_calls(monkeypatch):
    clear_calls = []

    def clear_app_runtime():
        clear_calls[-1].append("clear_app_runtime")

    monkeypatch.setattr(runtime_lifecycle, "clear_app_runtime", clear_app_runtime)
    return clear_calls


def bind_clear_calls(runtime_event_loop_clear_calls, handles):
    runtime_event_loop_clear_calls.append(handles.calls)


def test_run_runtime_event_loop_happy_path_order_and_return_value(runtime_event_loop_clear_calls):
    handles = make_runtime_event_loop_handles()
    bind_clear_calls(runtime_event_loop_clear_calls, handles)

    result = run_runtime_event_loop(handles)

    assert result == 7
    assert handles.calls == [
        "workers.start_all",
        "window.show",
        "app.exec",
        "workers.stop_all",
        "chat_history.save",
        "clear_app_runtime",
    ]


def test_run_runtime_event_loop_closes_mcp_controller_before_clearing_runtime(runtime_event_loop_clear_calls):
    handles = make_runtime_event_loop_handles()
    bind_clear_calls(runtime_event_loop_clear_calls, handles)
    close_calls = []
    handles.mcp_controller = SimpleNamespace(close_all=lambda: (close_calls.append("mcp_controller.close_all"), handles.calls.append("mcp_controller.close_all")))

    run_runtime_event_loop(handles)

    assert handles.calls == [
        "workers.start_all",
        "window.show",
        "app.exec",
        "workers.stop_all",
        "chat_history.save",
        "mcp_controller.close_all",
        "clear_app_runtime",
    ]
    assert close_calls == ["mcp_controller.close_all"]


def test_run_runtime_event_loop_still_closes_mcp_controller_when_exec_raises(runtime_event_loop_clear_calls):
    exec_error = RuntimeError("exec failed")
    handles = make_runtime_event_loop_handles(exec_error=exec_error)
    bind_clear_calls(runtime_event_loop_clear_calls, handles)
    handles.mcp_controller = SimpleNamespace(close_all=lambda: handles.calls.append("mcp_controller.close_all"))

    with pytest.raises(RuntimeError, match="exec failed"):
        run_runtime_event_loop(handles)

    assert handles.calls == [
        "workers.start_all",
        "window.show",
        "app.exec",
        "workers.stop_all",
        "chat_history.save",
        "mcp_controller.close_all",
        "clear_app_runtime",
    ]


def test_run_runtime_event_loop_preserves_save_exception_when_mcp_close_also_raises(runtime_event_loop_clear_calls):
    save_error = RuntimeError("save failed")
    close_error = RuntimeError("mcp close failed")
    handles = make_runtime_event_loop_handles(save_error=save_error)
    bind_clear_calls(runtime_event_loop_clear_calls, handles)

    def close_all():
        handles.calls.append("mcp_controller.close_all")
        raise close_error

    handles.mcp_controller = SimpleNamespace(close_all=close_all)

    with pytest.raises(RuntimeError, match="mcp close failed") as exc_info:
        run_runtime_event_loop(handles)

    assert exc_info.value is close_error
    assert exc_info.value.__context__ is save_error
    assert handles.calls == [
        "workers.start_all",
        "window.show",
        "app.exec",
        "workers.stop_all",
        "chat_history.save",
        "mcp_controller.close_all",
        "clear_app_runtime",
    ]


def test_run_runtime_event_loop_still_clears_runtime_when_mcp_close_is_already_safe(runtime_event_loop_clear_calls):
    handles = make_runtime_event_loop_handles()
    bind_clear_calls(runtime_event_loop_clear_calls, handles)

    def close_all():
        handles.calls.append("mcp_controller.close_all")
        return None

    handles.mcp_controller = SimpleNamespace(close_all=close_all)

    result = run_runtime_event_loop(handles)

    assert result == 7
    assert handles.calls == [
        "workers.start_all",
        "window.show",
        "app.exec",
        "workers.stop_all",
        "chat_history.save",
        "mcp_controller.close_all",
        "clear_app_runtime",
    ]


def test_run_runtime_event_loop_cleans_up_when_exec_raises(runtime_event_loop_clear_calls):
    exec_error = RuntimeError("exec failed")
    handles = make_runtime_event_loop_handles(exec_error=exec_error)
    bind_clear_calls(runtime_event_loop_clear_calls, handles)

    with pytest.raises(RuntimeError, match="exec failed") as exc_info:
        run_runtime_event_loop(handles)

    assert exc_info.value is exec_error
    assert handles.calls == [
        "workers.start_all",
        "window.show",
        "app.exec",
        "workers.stop_all",
        "chat_history.save",
        "clear_app_runtime",
    ]


def test_run_runtime_event_loop_cleans_up_when_start_all_raises(runtime_event_loop_clear_calls):
    start_error = RuntimeError("start failed")
    handles = make_runtime_event_loop_handles(start_error=start_error)
    bind_clear_calls(runtime_event_loop_clear_calls, handles)

    with pytest.raises(RuntimeError, match="start failed") as exc_info:
        run_runtime_event_loop(handles)

    assert exc_info.value is start_error
    assert handles.calls == [
        "workers.start_all",
        "workers.stop_all",
        "chat_history.save",
        "clear_app_runtime",
    ]


def test_run_runtime_event_loop_saves_history_and_propagates_stop_all_exception(runtime_event_loop_clear_calls):
    stop_error = RuntimeError("stop failed")
    handles = make_runtime_event_loop_handles(stop_error=stop_error)
    bind_clear_calls(runtime_event_loop_clear_calls, handles)

    with pytest.raises(RuntimeError, match="stop failed") as exc_info:
        run_runtime_event_loop(handles)

    assert exc_info.value is stop_error
    assert handles.calls == [
        "workers.start_all",
        "window.show",
        "app.exec",
        "workers.stop_all",
        "chat_history.save",
        "clear_app_runtime",
    ]


def test_run_runtime_event_loop_prioritizes_save_exception_after_stop_all_exception(runtime_event_loop_clear_calls):
    stop_error = RuntimeError("stop failed")
    save_error = RuntimeError("save failed")
    handles = make_runtime_event_loop_handles(stop_error=stop_error, save_error=save_error)
    bind_clear_calls(runtime_event_loop_clear_calls, handles)

    with pytest.raises(RuntimeError, match="save failed") as exc_info:
        run_runtime_event_loop(handles)

    assert exc_info.value is save_error
    assert exc_info.value.__context__ is stop_error
    assert handles.calls == [
        "workers.start_all",
        "window.show",
        "app.exec",
        "workers.stop_all",
        "chat_history.save",
        "clear_app_runtime",
    ]


def test_run_runtime_event_loop_prioritizes_save_exception_after_exec_exception(runtime_event_loop_clear_calls):
    exec_error = RuntimeError("exec failed")
    save_error = RuntimeError("save failed")
    handles = make_runtime_event_loop_handles(exec_error=exec_error, save_error=save_error)
    bind_clear_calls(runtime_event_loop_clear_calls, handles)

    with pytest.raises(RuntimeError, match="save failed") as exc_info:
        run_runtime_event_loop(handles)

    assert exc_info.value is save_error
    assert exc_info.value.__context__ is exec_error
    assert handles.calls == [
        "workers.start_all",
        "window.show",
        "app.exec",
        "workers.stop_all",
        "chat_history.save",
        "clear_app_runtime",
    ]
