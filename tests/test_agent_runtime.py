from core.runtime.agent_runtime import run_user_turn
from core.runtime.tool_summary import ToolInvocationRecord, ToolLoopTurnResult, ToolTurnSummary
from llm.llm_manager import LLMManager
from llm.tools.tool_manager import ToolManager


class DummyAdapter:
    def generate(self, messages, *, tools=None, generation_config=None):
        raise AssertionError("adapter.generate should not be called directly in these tests")


class RecordingToolManager(ToolManager):
    def __init__(self):
        super().__init__()
        self.calls = []

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return super().call_tool(name, arguments)


class StubLoopRunner:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, *, messages, adapter, tool_manager, generation_config=None, max_loops=3):
        self.calls.append(
            {
                "messages": [dict(message) for message in messages],
                "adapter": adapter,
                "tool_manager": tool_manager,
                "generation_config": generation_config,
                "max_loops": max_loops,
            }
        )
        return self.result


class ExplodingLoopRunner:
    def __call__(self, *, messages, adapter, tool_manager, generation_config=None, max_loops=3):
        raise RuntimeError("loop failure")


def build_manager(existing_messages=None):
    manager = LLMManager(
        adapter=DummyAdapter(),
        user_template="System prompt.",
        generation_config={"temperature": 0.2, "max_tokens": 111},
    )
    if existing_messages is not None:
        manager.set_messages(existing_messages)
    return manager


def build_tool_manager():
    manager = RecordingToolManager()
    manager.register(
        "echo_tool",
        lambda text: {"echo": text},
        description="Echo a text input",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    )
    return manager


def test_run_user_turn_appends_user_message_and_packages_loop_result():
    manager = build_manager(
        existing_messages=[
            {"role": "system", "content": "System prompt."},
            {"role": "assistant", "content": "Earlier reply."},
        ]
    )
    tool_manager = build_tool_manager()
    records = [
        ToolInvocationRecord(
            order_index=0,
            tool_name="echo_tool",
            status="success",
            arguments_summary='{"text": "hello"}',
            result_summary='{"echo": "hello"}',
        )
    ]
    packaged_result = ToolLoopTurnResult(
        final_output="Tool-backed answer.",
        invocation_records=records,
        summary=ToolTurnSummary.from_records(records),
        updated_messages=[
            {"role": "system", "content": "System prompt."},
            {"role": "assistant", "content": "Earlier reply."},
            {"role": "user", "content": "Hello runtime"},
            {"role": "assistant", "content": "Tool-backed answer."},
        ],
    )
    loop_runner = StubLoopRunner(packaged_result)

    result = run_user_turn(
        llm_manager=manager,
        tool_manager=tool_manager,
        user_text="Hello runtime",
        loop_runner=loop_runner,
        max_loops=5,
    )

    assert result is packaged_result
    assert len(loop_runner.calls) == 1
    assert loop_runner.calls[0]["messages"][:2] == [
        {"role": "system", "content": "System prompt."},
        {"role": "assistant", "content": "Earlier reply."},
    ]
    assert loop_runner.calls[0]["messages"][2]["role"] == "user"
    assert loop_runner.calls[0]["messages"][2]["content"].endswith("\nHello runtime")
    assert loop_runner.calls[0]["adapter"] is manager.adapter
    assert loop_runner.calls[0]["tool_manager"] is tool_manager
    assert loop_runner.calls[0]["generation_config"] == {"temperature": 0.2, "max_tokens": 111}
    assert loop_runner.calls[0]["max_loops"] == 5
    assert manager.get_messages() == packaged_result.updated_messages


def test_run_user_turn_updates_manager_with_safe_result_after_failed_tool_turn():
    manager = build_manager(existing_messages=[{"role": "system", "content": "System prompt."}])
    tool_manager = build_tool_manager()
    records = [
        ToolInvocationRecord(
            order_index=0,
            tool_name="echo_tool",
            status="failed",
            arguments_summary='{"text": "oops"}',
            error_summary="tool failed",
        )
    ]
    packaged_result = ToolLoopTurnResult(
        final_output="Sorry, something went wrong.",
        invocation_records=records,
        summary=ToolTurnSummary.from_records(records),
        updated_messages=[
            {"role": "system", "content": "System prompt."},
            {"role": "user", "content": "Trigger safe failure"},
            {"role": "assistant", "content": "Sorry, something went wrong."},
        ],
    )

    result = run_user_turn(
        llm_manager=manager,
        tool_manager=tool_manager,
        user_text="Trigger safe failure",
        loop_runner=StubLoopRunner(packaged_result),
    )

    assert result.final_output == "Sorry, something went wrong."
    assert result.summary.failure_count == 1
    assert manager.get_messages() == packaged_result.updated_messages


def test_run_user_turn_leaves_manager_history_unchanged_when_loop_runner_raises():
    existing_messages = [
        {"role": "system", "content": "System prompt."},
        {"role": "assistant", "content": "Earlier reply."},
    ]
    manager = build_manager(existing_messages=existing_messages)

    try:
        run_user_turn(
            llm_manager=manager,
            tool_manager=build_tool_manager(),
            user_text="This turn explodes",
            loop_runner=ExplodingLoopRunner(),
        )
    except RuntimeError as exc:
        assert str(exc) == "loop failure"
    else:
        raise AssertionError("Expected the loop failure to be raised")

    assert manager.get_messages() == existing_messages
