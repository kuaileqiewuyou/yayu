from __future__ import annotations

from typing import Any


def namespace_mcp_tool_name(server_name: str, tool_name: str) -> str:
    return f"{server_name}.{tool_name}"


def build_mcp_tool_definition(server_name: str, tool: dict[str, Any]) -> dict[str, Any]:
    input_schema = tool.get("inputSchema") or {
        "type": "object",
        "properties": {},
    }
    return {
        "type": "function",
        "function": {
            "name": namespace_mcp_tool_name(server_name, tool["name"]),
            "description": tool.get("description", ""),
            "parameters": input_schema,
        },
    }
