from core.runtime.tool_summary import (
    ToolInvocationRecord,
    ToolLoopTurnResult,
    ToolTurnSummary,
)


def test_tool_invocation_record_preserves_structured_fields():
    record = ToolInvocationRecord(
        order_index=0,
        tool_name="echo_tool",
        status="success",
        arguments_summary="text=hello",
        result_summary="echo:hello",
    )

    assert record.order_index == 0
    assert record.tool_name == "echo_tool"
    assert record.status == "success"
    assert record.arguments_summary == "text=hello"
    assert record.result_summary == "echo:hello"
    assert record.error_summary is None


def test_tool_turn_summary_counts_success_and_failure_records():
    summary = ToolTurnSummary.from_records(
        [
            ToolInvocationRecord(
                order_index=0,
                tool_name="echo_tool",
                status="success",
                arguments_summary="text=hello",
                result_summary="echo:hello",
            ),
            ToolInvocationRecord(
                order_index=1,
                tool_name="fail_tool",
                status="failed",
                arguments_summary="reason=boom",
                error_summary="boom",
            ),
        ]
    )

    assert summary.total_count == 2
    assert summary.success_count == 1
    assert summary.failure_count == 1


def test_tool_loop_turn_result_packages_output_records_and_summary():
    records = [
        ToolInvocationRecord(
            order_index=0,
            tool_name="echo_tool",
            status="success",
            arguments_summary="text=hello",
            result_summary="echo:hello",
        )
    ]
    summary = ToolTurnSummary.from_records(records)

    result = ToolLoopTurnResult(
        final_output="Done.",
        invocation_records=records,
        summary=summary,
    )

    assert result.final_output == "Done."
    assert result.invocation_records == records
    assert result.summary == summary
