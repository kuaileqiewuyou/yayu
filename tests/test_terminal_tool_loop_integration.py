from core.runtime.tool_loop import run_serial_tool_loop
from llm.tools.tool_manager import ToolManager
from llm.tools.terminal_tool import register_terminal_tool


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
    manager = ToolManager()
    register_terminal_tool(manager)
    return manager


def test_unified_tool_loop_can_execute_terminal_tool_and_reinject_result(tmp_path):
    workdir = str(tmp_path).replace("\\", "\\\\")
    tool_arguments = (
        '{"command": "printf \'hello\'", '
        f'"workdir": "{workdir}", '
        '"timeout": 5}'
    )
    adapter = FakeAdapter(
        [
            make_assistant_response(
                "",
                tool_calls=[make_tool_call("terminal", tool_arguments)],
            ),
            make_assistant_response("Terminal finished."),
        ]
    )
    tool_manager = build_tool_manager()

    result = run_serial_tool_loop(
        messages=[{"role": "user", "content": "Run terminal."}],
        adapter=adapter,
        tool_manager=tool_manager,
    )

    assert result.final_output == "Terminal finished."
    assert [record.tool_name for record in result.invocation_records] == ["terminal"]
    assert result.invocation_records[0].status == "success"
    assert result.summary.total_count == 1
    assert len(adapter.calls) == 2
    assert adapter.calls[0]["tools"] == tool_manager.get_tool_definitions()
    assert adapter.calls[1]["messages"][-1]["name"] == "terminal"


def test_unified_tool_loop_can_finish_after_terminal_tool_non_zero_result(tmp_path):
    workdir = str(tmp_path).replace("\\", "\\\\")
    tool_arguments = (
        '{"command": "sh -c \'echo boom >&2; exit 9\'", '
        f'"workdir": "{workdir}", '
        '"timeout": 5}'
    )
    adapter = FakeAdapter(
        [
            make_assistant_response(
                "",
                tool_calls=[make_tool_call("terminal", tool_arguments)],
            ),
            make_assistant_response("Terminal failure was observed."),
        ]
    )
    tool_manager = build_tool_manager()

    result = run_serial_tool_loop(
        messages=[{"role": "user", "content": "Run failing terminal command."}],
        adapter=adapter,
        tool_manager=tool_manager,
    )

    assert result.final_output == "Terminal failure was observed."
    assert [record.tool_name for record in result.invocation_records] == ["terminal"]
    assert result.invocation_records[0].status == "success"
    assert result.summary.total_count == 1
    assert len(adapter.calls) == 2


def test_unified_tool_loop_preserves_terminal_approval_request_for_trusted_ui(tmp_path):
    workdir = str(tmp_path).replace("\\", "\\\\")
    arguments = (
        '{"command": "rm -rf protected", '
        f'"workdir": "{workdir}", '
        '"timeout": 5}'
    )
    adapter = FakeAdapter([
        make_assistant_response("", tool_calls=[make_tool_call("terminal", arguments)]),
        make_assistant_response("需要你的批准。"),
    ])

    result = run_serial_tool_loop(
        messages=[{"role": "user", "content": "删除 protected"}],
        adapter=adapter,
        tool_manager=build_tool_manager(),
    )

    approval = result.invocation_records[0].approval_request
    assert approval is not None
    assert approval["approval_required"] is True
    assert approval["pending_decision_id"].startswith("decision-")
