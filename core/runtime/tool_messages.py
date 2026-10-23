import json


TOOL_RESULT_STATUS_SUCCESS = "success"
TOOL_RESULT_STATUS_FAILED = "failed"


def normalize_tool_summary(value: object) -> str:
    if isinstance(value, str):
        return " ".join(value.split())

    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def build_success_tool_result_message(tool_name: str, raw_result: object, tool_call_id: str) -> dict[str, object]:
    return {
        "role": "tool",
        "name": tool_name,
        "tool_call_id": tool_call_id,
        "content": normalize_tool_summary(raw_result),
    }


def build_failed_tool_result_message(tool_name: str, error_summary: str, tool_call_id: str) -> dict[str, object]:
    return {
        "role": "tool",
        "name": tool_name,
        "tool_call_id": tool_call_id,
        "content": normalize_tool_summary(error_summary),
    }
