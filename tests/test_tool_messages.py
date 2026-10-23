from core.runtime.tool_messages import (
    TOOL_RESULT_STATUS_FAILED,
    TOOL_RESULT_STATUS_SUCCESS,
    build_failed_tool_result_message,
    build_success_tool_result_message,
    normalize_tool_summary,
)


def test_build_success_tool_result_message_keeps_tool_role_name_and_raw_result():
    message = build_success_tool_result_message(
        tool_name="echo_tool",
        raw_result={"echo": "hello"},
        tool_call_id="call-1",
    )

    assert message["role"] == "tool"
    assert message["name"] == "echo_tool"
    assert message["tool_call_id"] == "call-1"
    assert message["content"] == '{"echo": "hello"}'


def test_build_failed_tool_result_message_keeps_tool_name_and_error_summary():
    message = build_failed_tool_result_message(
        tool_name="fail_tool",
        error_summary="boom",
        tool_call_id="call-2",
    )

    assert message["role"] == "tool"
    assert message["name"] == "fail_tool"
    assert message["tool_call_id"] == "call-2"
    assert message["content"] == "boom"


def test_normalize_tool_summary_returns_stable_single_line_strings():
    assert normalize_tool_summary("  hello\nworld  ") == "hello world"
    assert normalize_tool_summary({"b": 2, "a": 1}) == '{"a": 1, "b": 2}'
