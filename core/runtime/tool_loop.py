import json
from core.runtime.cancellation import check_cancelled

from llm.tools.tool_manager import ToolExecutionResult

from core.runtime.tool_messages import (
    build_failed_tool_result_message,
    build_success_tool_result_message,
    normalize_tool_summary,
)
from core.runtime.tool_summary import ToolInvocationRecord, ToolLoopTurnResult, ToolTurnSummary


LOOP_CAP_MESSAGE = "Tool loop stopped after reaching the maximum loop count."
MALFORMED_TOOL_CALL_MESSAGE = "Tool loop failed due to malformed tool call data."


def _emit_progress(progress_callback, text: str) -> None:
    if progress_callback is None or not text:
        return
    try:
        progress_callback(text)
    except Exception:
        # 进度展示不能影响模型或工具本身的执行。
        return


def _short_progress_value(value: object, limit: int = 72) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[:limit - 1]}…"


def _tool_progress_text(tool_name: str, arguments: dict, *, completed: bool = False, success: bool = True) -> str:
    if completed:
        suffix = "完成" if success else "失败"
        labels = {
            "get_workspace_info": "工作区信息查询",
            "web_search": "联网搜索",
            "web_extract": "网页读取",
            "read_file": "文件读取",
            "search_files": "项目搜索",
            "list_directory": "目录查看",
            "write_file": "文件写入",
            "patch_file": "文件修改",
            "terminal": "命令执行",
            "process": "后台进程操作",
        }
        return f"{labels.get(tool_name, f'工具 {tool_name}')} {suffix}"

    if tool_name == "get_workspace_info":
        return "正在查看工作区信息"
    if tool_name == "web_search":
        return f"正在联网搜索：{_short_progress_value(arguments.get('query'))}"
    if tool_name == "web_extract":
        return f"正在读取网页：{_short_progress_value(arguments.get('urls') or arguments.get('url'))}"
    if tool_name == "read_file":
        return f"正在读取文件：{_short_progress_value(arguments.get('path'))}"
    if tool_name == "search_files":
        return f"正在搜索项目文件：{_short_progress_value(arguments.get('query'))}"
    if tool_name == "list_directory":
        return f"正在查看目录：{_short_progress_value(arguments.get('path'))}"
    if tool_name in {"write_file", "patch_file"}:
        return f"正在修改文件：{_short_progress_value(arguments.get('path'))}"
    if tool_name == "terminal":
        return f"正在执行命令：{_short_progress_value(arguments.get('command'))}"
    if tool_name == "process":
        return f"正在操作后台进程：{_short_progress_value(arguments.get('action'))}"
    return f"正在调用工具：{tool_name}"


def _normalize_response(response) -> dict:
    if isinstance(response, dict):
        return response
    if hasattr(response, "choices") and response.choices:
        message = getattr(response.choices[0], "message", None)
        if message is None:
            return {"content": "", "tool_calls": []}
        content = getattr(message, "content", "") or ""
        tool_calls = getattr(message, "tool_calls", None)
        if not isinstance(tool_calls, list):
            tool_calls = []
        return {
            "content": content,
            "tool_calls": [_normalize_tool_call(tool_call) for tool_call in tool_calls],
        }
    return {"content": str(response), "tool_calls": []}


def _normalize_tool_call(tool_call) -> dict:
    if isinstance(tool_call, dict):
        return tool_call
    function = getattr(tool_call, "function", None)
    return {
        "id": getattr(tool_call, "id", ""),
        "type": getattr(tool_call, "type", "function"),
        "function": {
            "name": getattr(function, "name", ""),
            "arguments": getattr(function, "arguments", "{}"),
        },
    }


def _extract_tool_calls(response: dict) -> list[dict]:
    tool_calls = response.get("tool_calls")
    if isinstance(tool_calls, list):
        return tool_calls
    return []


def _parse_arguments(raw_arguments: object) -> dict:
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if isinstance(raw_arguments, str):
        parsed = json.loads(raw_arguments)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Malformed tool arguments")


def _build_record(order_index: int, tool_name: str, arguments: dict, execution_result: ToolExecutionResult) -> ToolInvocationRecord:
    if not execution_result.success:
        approval_request = None
        if isinstance(execution_result.value, dict) and execution_result.value.get("approval_required") is True:
            approval_request = dict(execution_result.value)
        return ToolInvocationRecord(
            order_index=order_index,
            tool_name=tool_name,
            status="failed",
            arguments_summary=normalize_tool_summary(arguments),
            error_summary=normalize_tool_summary(execution_result.error or "Tool call failed"),
            approval_request=approval_request,
        )

    return ToolInvocationRecord(
        order_index=order_index,
        tool_name=tool_name,
        status="success",
        arguments_summary=normalize_tool_summary(arguments),
        result_summary=normalize_tool_summary(execution_result.value),
    )


def _build_tool_result_message(record: ToolInvocationRecord, execution_result: ToolExecutionResult, tool_call_id: str) -> dict[str, object]:
    if record.status == "failed":
        return build_failed_tool_result_message(record.tool_name, record.error_summary or "Tool call failed", tool_call_id)
    return build_success_tool_result_message(record.tool_name, execution_result.value, tool_call_id)


def _build_safe_failure_result(message: str, records: list[ToolInvocationRecord], working_messages: list[dict[str, str]]) -> ToolLoopTurnResult:
    updated_messages = [*working_messages, {"role": "assistant", "content": message}]
    return ToolLoopTurnResult(
        final_output=message,
        invocation_records=records,
        summary=ToolTurnSummary.from_records(records),
        updated_messages=updated_messages,
    )


def run_serial_tool_loop(messages, adapter, tool_manager, generation_config=None, max_loops=6, progress_callback=None, text_callback=None, context_limit=None):
    working_messages = [dict(message) for message in messages]
    invocation_records: list[ToolInvocationRecord] = []
    order_index = 0

    # 新一轮循环开始：重置工具配额计数（上一轮的使用不计入本轮）。
    reset_quotas = getattr(tool_manager, "reset_quotas", None)
    if callable(reset_quotas):
        reset_quotas()

    for loop_index in range(max_loops + 1):
        check_cancelled()
        request_messages = working_messages
        if context_limit:
            from llm.compact_manager import CompactManager
            request_messages = CompactManager(context_limit).fit_request(
                working_messages, tools=tool_manager.get_tool_definitions(),
                reply_tokens=(generation_config or {}).get("max_tokens", 4096))
        _emit_progress(progress_callback, "正在请求模型..." if loop_index == 0 else "正在结合工具结果继续思考...")
        stream_generate = getattr(adapter, "generate_stream", None)
        if text_callback is not None and callable(stream_generate):
            text_callback(None)  # A fresh parser for each model response after tools.
            response = stream_generate(
                request_messages, tools=tool_manager.get_tool_definitions(),
                generation_config=generation_config, on_text=text_callback,
            )
        else:
            response = adapter.generate(
                request_messages, tools=tool_manager.get_tool_definitions(),
                generation_config=generation_config,
            )
        check_cancelled()
        normalized_response = _normalize_response(response)
        tool_calls = _extract_tool_calls(normalized_response)
        if not tool_calls:
            _emit_progress(progress_callback, "模型已生成回复")
            return ToolLoopTurnResult(
                final_output=normalized_response.get("content", ""),
                invocation_records=invocation_records,
                summary=ToolTurnSummary.from_records(invocation_records),
                updated_messages=[*working_messages, {"role": "assistant", "content": normalized_response.get("content", "")}],
            )

        if loop_index >= max_loops:
            invocation_records.append(
                ToolInvocationRecord(
                    order_index=order_index,
                    tool_name="tool_loop",
                    status="failed",
                    arguments_summary="{}",
                    error_summary="Tool loop stopped after reaching the maximum loop count.",
                )
            )
            return _build_safe_failure_result(LOOP_CAP_MESSAGE, invocation_records, working_messages)

        working_messages.append({
            "role": "assistant",
            "content": normalized_response.get("content", ""),
            "tool_calls": tool_calls,
        })
        for tool_call in tool_calls:
            check_cancelled()
            function_payload = tool_call.get("function")
            if not isinstance(function_payload, dict):
                invocation_records.append(
                    ToolInvocationRecord(
                        order_index=order_index,
                        tool_name="unknown_tool",
                        status="failed",
                        arguments_summary="{}",
                        error_summary="Malformed tool call payload.",
                    )
                )
                return _build_safe_failure_result(MALFORMED_TOOL_CALL_MESSAGE, invocation_records, working_messages)

            tool_name = function_payload.get("name")
            if not isinstance(tool_name, str) or not tool_name:
                invocation_records.append(
                    ToolInvocationRecord(
                        order_index=order_index,
                        tool_name="unknown_tool",
                        status="failed",
                        arguments_summary="{}",
                        error_summary="Malformed tool call payload.",
                    )
                )
                return _build_safe_failure_result(MALFORMED_TOOL_CALL_MESSAGE, invocation_records, working_messages)

            try:
                arguments = _parse_arguments(function_payload.get("arguments", {}))
            except Exception:
                invocation_records.append(
                    ToolInvocationRecord(
                        order_index=order_index,
                        tool_name=tool_name,
                        status="failed",
                        arguments_summary=normalize_tool_summary(function_payload.get("arguments", {})),
                        error_summary="Malformed tool call payload.",
                    )
                )
                return _build_safe_failure_result(MALFORMED_TOOL_CALL_MESSAGE, invocation_records, working_messages)

            _emit_progress(progress_callback, _tool_progress_text(tool_name, arguments))
            execution_result = tool_manager.call_tool(tool_name, arguments)
            check_cancelled()
            record = _build_record(order_index, tool_name, arguments, execution_result)
            invocation_records.append(record)
            _emit_progress(
                progress_callback,
                _tool_progress_text(
                    tool_name,
                    arguments,
                    completed=True,
                    success=execution_result.success,
                ),
            )
            tool_call_id = tool_call.get("id") or f"call-{order_index + 1}"
            working_messages.append(_build_tool_result_message(record, execution_result, tool_call_id))
            order_index += 1

    invocation_records.append(
        ToolInvocationRecord(
            order_index=order_index,
            tool_name="tool_loop",
            status="failed",
            arguments_summary="{}",
            error_summary="Tool loop stopped after reaching the maximum loop count.",
        )
    )
    return _build_safe_failure_result(LOOP_CAP_MESSAGE, invocation_records, working_messages)
