from __future__ import annotations

from typing import Callable, Iterable, Any

from core.mcp.config import MCPServerConfig
from core.mcp.status import MCPServerStatus, MCPStatusSnapshot
from llm.tools.tool_manager import ToolManager


def register_mcp_tools(
    *,
    tool_manager: ToolManager,
    server_configs: Iterable[MCPServerConfig],
    session_factory: Callable[[MCPServerConfig], Any],
) -> MCPStatusSnapshot:
    configs = list(server_configs)
    if not configs:
        return MCPStatusSnapshot(state="disabled")

    statuses: list[MCPServerStatus] = []
    for config in configs:
        try:
            session = session_factory(config)
            tools = session.list_tools()
            for tool in tools:
                tool_manager.register_mcp_tool(
                    server_name=config.name,
                    tool_name=tool["name"],
                    session=session,
                    description=tool.get("description", ""),
                    parameters=tool.get("inputSchema") or {"type": "object", "properties": {}},
                )
            statuses.append(
                MCPServerStatus(
                    name=config.name,
                    transport=config.transport,
                    enabled=config.enabled,
                    state="ready",
                    tool_count=len(tools),
                )
            )
        except Exception as exc:
            statuses.append(
                MCPServerStatus(
                    name=config.name,
                    transport=config.transport,
                    enabled=config.enabled,
                    state="failed",
                    error=str(exc),
                )
            )

    ready_count = sum(1 for status in statuses if status.state == "ready")
    failed_count = sum(1 for status in statuses if status.state == "failed")
    if ready_count and failed_count:
        overall_state = "partial"
    elif ready_count:
        overall_state = "ready"
    else:
        overall_state = "failed"

    return MCPStatusSnapshot(state=overall_state, servers=statuses)
