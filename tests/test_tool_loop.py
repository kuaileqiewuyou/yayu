from llm.tools.tool_manager import ToolExecutionResult, ToolManager

from sdk.adapters import LLMAdapter
from core.runtime.tool_loop import run_serial_tool_loop
from core.runtime.tool_messages import TOOL_RESULT_STATUS_FAILED, TOOL_RESULT_STATUS_SUCCESS


class FakeAdapter:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def generate(self, messages, *, tools=None, generation_config=None):
        self.calls.append(
            {
                "messages": [dict(message) for message in messages],
                "tools": tools,
                "generation_config": generation_config,
            }
        )
        return self._responses.pop(0)


class ChatOnlyAdapter(LLMAdapter):
    def __init__(self, responses):
        super().__init__()
        self._responses = list(responses)
        self.calls = []

    def chat(self, messages, stream=False, **kwargs):
        self.calls.append(
            {
                "messages": [dict(message) for message in messages],
                "stream": stream,
                "kwargs": kwargs,
            }
        )
        return self._responses.pop(0)


class TrackingToolManager(ToolManager):
    def __init__(self):
        super().__init__()
        self.calls = []

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return super().call_tool(name, arguments)


def echo_tool(text):
    return {"echo": text}


def lookup_fact(key):
    facts = {"planet": "Earth", "language": "Python"}
    return {"value": facts[key]}


def fail_tool(reason):
    raise RuntimeError(reason)


def make_tool_call(tool_name, arguments, tool_call_id="call-1"):
    return {
        "id": tool_call_id,
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": arguments,
        },
    }


def make_assistant_response(content, tool_calls=None):
    response = {
        "role": "assistant",
        "content": content,
    }
    if tool_calls is not None:
        response["tool_calls"] = tool_calls
    return response


def build_tool_manager():
    manager = TrackingToolManager()
    manager.register(
        "echo_tool",
        echo_tool,
        description="Echo a text input",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    )
    manager.register(
        "lookup_fact",
        lookup_fact,
        description="Look up a fixed fact",
        parameters={
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
    )
    manager.register(
        "fail_tool",
        fail_tool,
        description="Raise a controlled failure",
        parameters={
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    )
    return manager


def test_run_serial_tool_loop_returns_immediate_final_response_when_no_tools_requested():
    adapter = FakeAdapter([make_assistant_response("Hello without tools.")])
    tool_manager = build_tool_manager()
    messages = [{"role": "user", "content": "Say hello."}]

    result = run_serial_tool_loop(messages=messages, adapter=adapter, tool_manager=tool_manager)

    assert result.final_output == "Hello without tools."
    assert result.invocation_records == []
    assert result.summary.total_count == 0
    assert tool_manager.calls == []
    assert len(adapter.calls) == 1
    assert adapter.calls[0]["messages"] == messages
    assert adapter.calls[0]["tools"] == tool_manager.get_tool_definitions()


def test_run_serial_tool_loop_reinjects_openai_compatible_assistant_and_tool_messages():
    adapter = FakeAdapter([
        make_assistant_response(
            "",
            tool_calls=[make_tool_call("echo_tool", '{"text": "hello"}', tool_call_id="call-wire")],
        ),
        make_assistant_response("done"),
    ])

    run_serial_tool_loop(
        messages=[{"role": "user", "content": "echo"}],
        adapter=adapter,
        tool_manager=build_tool_manager(),
    )

    reinjected = adapter.calls[1]["messages"][-2:]
    assert reinjected[0]["role"] == "assistant"
    assert reinjected[0]["tool_calls"][0]["id"] == "call-wire"
    assert reinjected[1] == {
        "role": "tool",
        "name": "echo_tool",
        "tool_call_id": "call-wire",
        "content": '{"echo": "hello"}',
    }


def test_run_serial_tool_loop_accepts_sdk_style_tool_call_objects():
    class SDKFunction:
        name = "echo_tool"
        arguments = '{"text": "hello"}'

    class SDKToolCall:
        id = "call-sdk"
        type = "function"
        function = SDKFunction()

    class SDKMessage:
        content = ""
        tool_calls = [SDKToolCall()]

    class SDKChoice:
        message = SDKMessage()

    class SDKResponse:
        choices = [SDKChoice()]

    adapter = FakeAdapter([SDKResponse(), make_assistant_response("done")])

    result = run_serial_tool_loop(
        messages=[{"role": "user", "content": "echo"}],
        adapter=adapter,
        tool_manager=build_tool_manager(),
    )

    assert result.final_output == "done"
    assert result.invocation_records[0].status == "success"


def test_run_serial_tool_loop_accepts_chat_only_adapter_via_llm_adapter_bridge():
    adapter = ChatOnlyAdapter([make_assistant_response("Hello from chat-only adapter.")])
    tool_manager = build_tool_manager()
    messages = [{"role": "user", "content": "Say hello through chat()."}]

    result = run_serial_tool_loop(messages=messages, adapter=adapter, tool_manager=tool_manager)

    assert result.final_output == "Hello from chat-only adapter."
    assert result.invocation_records == []
    assert tool_manager.calls == []
    assert len(adapter.calls) == 1
    assert adapter.calls[0]["messages"] == messages
    assert adapter.calls[0]["stream"] is False
    assert adapter.calls[0]["kwargs"]["tools"] == tool_manager.get_tool_definitions()
    assert adapter.calls[0]["kwargs"].get("generation_config") is None


def test_run_serial_tool_loop_executes_single_tool_and_reinjects_result_before_final_answer():
    adapter = FakeAdapter(
        [
            make_assistant_response(
                "",
                tool_calls=[make_tool_call("echo_tool", '{"text": "hello"}')],
            ),
            make_assistant_response("Final answer after tool."),
        ]
    )
    tool_manager = build_tool_manager()
    messages = [{"role": "user", "content": "Echo hello."}]

    result = run_serial_tool_loop(messages=messages, adapter=adapter, tool_manager=tool_manager)

    assert result.final_output == "Final answer after tool."
    assert [record.tool_name for record in result.invocation_records] == ["echo_tool"]
    assert result.invocation_records[0].status == "success"
    assert result.summary.total_count == 1
    assert result.summary.success_count == 1
    assert tool_manager.calls == [("echo_tool", {"text": "hello"})]
    assert len(adapter.calls) == 2
    reinjected_messages = adapter.calls[1]["messages"]
    assert reinjected_messages[-2]["role"] == "assistant"
    assert reinjected_messages[-1] == {
        "role": "tool",
        "name": "echo_tool",
        "tool_call_id": "call-1",
        "content": '{"echo": "hello"}',
    }



def test_run_serial_tool_loop_supports_multi_step_serialized_execution():
    adapter = FakeAdapter(
        [
            make_assistant_response(
                "",
                tool_calls=[make_tool_call("echo_tool", '{"text": "hello"}', tool_call_id="call-1")],
            ),
            make_assistant_response(
                "",
                tool_calls=[make_tool_call("lookup_fact", '{"key": "planet"}', tool_call_id="call-2")],
            ),
            make_assistant_response("Final answer after two tools."),
        ]
    )
    tool_manager = build_tool_manager()

    result = run_serial_tool_loop(
        messages=[{"role": "user", "content": "Use two tools."}],
        adapter=adapter,
        tool_manager=tool_manager,
    )

    assert result.final_output == "Final answer after two tools."
    assert [record.tool_name for record in result.invocation_records] == ["echo_tool", "lookup_fact"]
    assert [record.order_index for record in result.invocation_records] == [0, 1]
    assert tool_manager.calls == [
        ("echo_tool", {"text": "hello"}),
        ("lookup_fact", {"key": "planet"}),
    ]
    assert len(adapter.calls) == 3
    assert adapter.calls[1]["messages"][-1]["name"] == "echo_tool"
    assert adapter.calls[2]["messages"][-3]["name"] == "echo_tool"
    assert adapter.calls[2]["messages"][-1]["name"] == "lookup_fact"



def test_run_serial_tool_loop_executes_same_response_tool_calls_in_order():
    adapter = FakeAdapter(
        [
            make_assistant_response(
                "",
                tool_calls=[
                    make_tool_call("echo_tool", '{"text": "first"}', tool_call_id="call-1"),
                    make_tool_call("lookup_fact", '{"key": "language"}', tool_call_id="call-2"),
                ],
            ),
            make_assistant_response("Final answer after ordered calls."),
        ]
    )
    tool_manager = build_tool_manager()

    result = run_serial_tool_loop(
        messages=[{"role": "user", "content": "Use two tools in one response."}],
        adapter=adapter,
        tool_manager=tool_manager,
    )

    assert tool_manager.calls == [
        ("echo_tool", {"text": "first"}),
        ("lookup_fact", {"key": "language"}),
    ]
    assert [record.order_index for record in result.invocation_records] == [0, 1]
    assert [record.tool_name for record in result.invocation_records] == ["echo_tool", "lookup_fact"]
    assert result.final_output == "Final answer after ordered calls."
    reinjected_messages = adapter.calls[1]["messages"]
    assert [message["name"] for message in reinjected_messages[-2:]] == ["echo_tool", "lookup_fact"]



def test_run_serial_tool_loop_records_failed_invocation_and_reinjects_failure_result():
    adapter = FakeAdapter(
        [
            make_assistant_response(
                "",
                tool_calls=[make_tool_call("fail_tool", '{"reason": "boom"}')],
            ),
            make_assistant_response("Recovered after failure."),
        ]
    )
    tool_manager = build_tool_manager()

    result = run_serial_tool_loop(
        messages=[{"role": "user", "content": "Trigger failure."}],
        adapter=adapter,
        tool_manager=tool_manager,
    )

    assert result.final_output == "Recovered after failure."
    assert result.summary.total_count == 1
    assert result.summary.failure_count == 1
    assert result.invocation_records[0].status == "failed"
    assert result.invocation_records[0].tool_name == "fail_tool"
    assert "boom" in result.invocation_records[0].error_summary
    assert adapter.calls[1]["messages"][-1] == {
        "role": "tool",
        "name": "fail_tool",
        "tool_call_id": "call-1",
        "content": "boom",
    }



def test_run_serial_tool_loop_does_not_infer_failure_from_localized_string_output():
    class StringReturningToolManager(TrackingToolManager):
        def call_tool(self, name, arguments):
            self.calls.append((name, arguments))
            return ToolExecutionResult(success=True, value="工具调用失败: this is plain tool output")

    adapter = FakeAdapter(
        [
            make_assistant_response(
                "",
                tool_calls=[make_tool_call("echo_tool", '{"text": "hello"}')],
            ),
            make_assistant_response("Accepted localized string output."),
        ]
    )
    tool_manager = StringReturningToolManager()
    tool_manager.register(
        "echo_tool",
        echo_tool,
        description="Echo a text input",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    )

    result = run_serial_tool_loop(
        messages=[{"role": "user", "content": "Return a literal localized string."}],
        adapter=adapter,
        tool_manager=tool_manager,
    )

    assert result.final_output == "Accepted localized string output."
    assert result.summary.success_count == 1
    assert result.summary.failure_count == 0
    assert result.invocation_records[0].status == "success"
    assert result.invocation_records[0].result_summary == "工具调用失败: this is plain tool output"
    assert adapter.calls[1]["messages"][-1] == {
        "role": "tool",
        "name": "echo_tool",
        "tool_call_id": "call-1",
        "content": "工具调用失败: this is plain tool output",
    }



def test_run_serial_tool_loop_records_unknown_tool_as_failed_invocation():
    adapter = FakeAdapter(
        [
            make_assistant_response(
                "",
                tool_calls=[make_tool_call("missing_tool", '{"value": 1}')],
            ),
            make_assistant_response("Handled unknown tool."),
        ]
    )
    tool_manager = build_tool_manager()

    result = run_serial_tool_loop(
        messages=[{"role": "user", "content": "Call a missing tool."}],
        adapter=adapter,
        tool_manager=tool_manager,
    )

    assert result.final_output == "Handled unknown tool."
    assert result.summary.failure_count == 1
    assert result.invocation_records[0].status == "failed"
    assert result.invocation_records[0].tool_name == "missing_tool"
    assert "missing_tool" in result.invocation_records[0].error_summary
    assert adapter.calls[1]["messages"][-1]["content"] == result.invocation_records[0].error_summary



def test_run_serial_tool_loop_stops_safely_when_loop_cap_is_exceeded():
    adapter = FakeAdapter(
        [
            make_assistant_response("", tool_calls=[make_tool_call("echo_tool", '{"text": "one"}')]),
            make_assistant_response("", tool_calls=[make_tool_call("echo_tool", '{"text": "two"}')]),
            make_assistant_response("", tool_calls=[make_tool_call("echo_tool", '{"text": "three"}')]),
        ]
    )
    tool_manager = build_tool_manager()

    result = run_serial_tool_loop(
        messages=[{"role": "user", "content": "Loop forever."}],
        adapter=adapter,
        tool_manager=tool_manager,
        max_loops=2,
    )

    assert result.final_output == "Tool loop stopped after reaching the maximum loop count."
    assert len(tool_manager.calls) == 2
    assert result.summary.total_count == 3
    assert result.summary.failure_count == 1
    assert result.invocation_records[-1].status == "failed"
    assert result.invocation_records[-1].tool_name == "tool_loop"
    assert "maximum loop count" in result.invocation_records[-1].error_summary



def test_run_serial_tool_loop_fails_safely_on_malformed_tool_call_payload():
    adapter = FakeAdapter(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "echo_tool",
                            "arguments": "{not-json}",
                        },
                    }
                ],
            }
        ]
    )
    tool_manager = build_tool_manager()

    result = run_serial_tool_loop(
        messages=[{"role": "user", "content": "Produce malformed tool call."}],
        adapter=adapter,
        tool_manager=tool_manager,
    )

    assert result.final_output == "Tool loop failed due to malformed tool call data."
    assert result.summary.total_count == 1
    assert result.summary.failure_count == 1
    assert result.invocation_records[0].status == "failed"
    assert result.invocation_records[0].tool_name == "echo_tool"
    assert "malformed" in result.invocation_records[0].error_summary.lower()
    assert tool_manager.calls == []
