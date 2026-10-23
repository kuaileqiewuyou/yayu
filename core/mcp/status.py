from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


MCPOverallState = Literal["disabled", "ready", "partial", "failed", "invalid_config"]
MCPServerState = Literal[
    "disabled",
    "ready",
    "start_failed",
    "discover_failed",
    "call_failed",
    "disconnected",
]


@dataclass(frozen=True)
class MCPServerStatus:
    name: str
    transport: str
    enabled: bool
    state: MCPServerState
    tool_count: int = 0
    error: str = ""
    discovered_tools: list[str] = field(default_factory=list)
    discovered_tool_descriptions: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MCPStatusSnapshot:
    state: MCPOverallState
    servers: list[MCPServerStatus] = field(default_factory=list)
    error: str = ""


def summarize_mcp_status(servers: list[MCPServerStatus]) -> MCPStatusSnapshot:
    if not servers:
        return MCPStatusSnapshot(state="disabled", servers=[])

    enabled_servers = [server for server in servers if server.enabled]
    if not enabled_servers:
        return MCPStatusSnapshot(state="disabled", servers=servers)

    ready_count = sum(1 for server in enabled_servers if server.state == "ready")
    failed_count = len(enabled_servers) - ready_count

    if ready_count and failed_count:
        overall_state: MCPOverallState = "partial"
    elif ready_count:
        overall_state = "ready"
    else:
        overall_state = "failed"

    return MCPStatusSnapshot(state=overall_state, servers=servers)
