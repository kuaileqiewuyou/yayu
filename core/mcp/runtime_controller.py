from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.mcp.client import MCPClientSession
from core.mcp.config import MCPServerConfig, load_mcp_server_configs
from core.mcp.status import MCPServerStatus, MCPStatusSnapshot, summarize_mcp_status
from core.mcp.transport_http import build_http_transport
from core.mcp.transport_stdio import build_stdio_transport


@dataclass
class MCPRuntimeController:
    config_path: Path = Path("data/config/mcp.yaml")
    _sessions: list[MCPClientSession] = field(default_factory=list)
    _last_snapshot: MCPStatusSnapshot = field(default_factory=lambda: MCPStatusSnapshot(state="disabled"))

    @property
    def last_snapshot(self) -> MCPStatusSnapshot:
        return self._last_snapshot

    def load_server_configs(self) -> list[MCPServerConfig]:
        try:
            return load_mcp_server_configs(self.config_path)
        except Exception as exc:
            self._last_snapshot = MCPStatusSnapshot(state="invalid_config", error=str(exc))
            return []

    def get_snapshot(self) -> MCPStatusSnapshot:
        return self._last_snapshot

    def register_into_tool_manager(self, manager: Any) -> MCPStatusSnapshot:
        self.close_all()
        configs = self.load_server_configs()
        if self._last_snapshot.state == "invalid_config":
            return self._last_snapshot
        if not configs:
            snapshot = MCPStatusSnapshot(state="disabled", servers=[])
            self._last_snapshot = snapshot
            return snapshot

        statuses: list[MCPServerStatus] = []
        for config in configs:
            if not config.enabled:
                statuses.append(
                    MCPServerStatus(
                        name=config.name,
                        transport=config.transport,
                        enabled=config.enabled,
                        state="disabled",
                    )
                )
                continue
            try:
                session = self._build_session(config)
            except Exception as exc:
                statuses.append(
                    MCPServerStatus(
                        name=config.name,
                        transport=config.transport,
                        enabled=config.enabled,
                        state="start_failed",
                        error=str(exc),
                    )
                )
                continue
            try:
                tools = session.list_tools()
                for tool in tools:
                    manager.register_mcp_tool(
                        server_name=config.name,
                        tool_name=tool["name"],
                        session=session,
                        description=tool.get("description", ""),
                        parameters=tool.get("inputSchema") or {"type": "object", "properties": {}},
                        on_call_failure=lambda error, server_name=config.name: self._mark_server_disconnected(server_name, error),
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
                        state="discover_failed",
                        error=str(exc),
                    )
                )

        snapshot = summarize_mcp_status(statuses)
        self._last_snapshot = snapshot
        return snapshot

    def redetect(self) -> MCPStatusSnapshot:
        configs = self.load_server_configs()
        if self._last_snapshot.state == "invalid_config":
            return self._last_snapshot
        return self.redetect_servers(configs)

    def redetect_servers(self, configs: list[MCPServerConfig]) -> MCPStatusSnapshot:
        self.close_all()
        if not configs:
            snapshot = MCPStatusSnapshot(state="disabled", servers=[])
            self._last_snapshot = snapshot
            return snapshot

        statuses: list[MCPServerStatus] = []
        for config in configs:
            if not config.enabled:
                statuses.append(
                    MCPServerStatus(
                        name=config.name,
                        transport=config.transport,
                        enabled=config.enabled,
                        state="disabled",
                    )
                )
                continue
            try:
                session = self._build_session(config)
            except Exception as exc:
                statuses.append(
                    MCPServerStatus(
                        name=config.name,
                        transport=config.transport,
                        enabled=config.enabled,
                        state="start_failed",
                        error=str(exc),
                    )
                )
                continue
            try:
                tools = session.list_tools()
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
                        state="discover_failed",
                        error=str(exc),
                    )
                )

        snapshot = summarize_mcp_status(statuses)
        self._last_snapshot = snapshot
        return snapshot

    def test_server(self, config: MCPServerConfig) -> MCPServerStatus:
        try:
            session = self._build_session(config)
        except Exception as exc:
            return MCPServerStatus(
                name=config.name,
                transport=config.transport,
                enabled=config.enabled,
                state="start_failed",
                error=str(exc),
            )
        try:
            tools = session.list_tools()
            return MCPServerStatus(
                name=config.name,
                transport=config.transport,
                enabled=config.enabled,
                state="ready",
                tool_count=len(tools),
            )
        except Exception as exc:
            return MCPServerStatus(
                name=config.name,
                transport=config.transport,
                enabled=config.enabled,
                state="discover_failed",
                error=str(exc),
            )

    def _mark_server_disconnected(self, server_name: str, error: str) -> None:
        servers: list[MCPServerStatus] = []
        for server in self._last_snapshot.servers:
            if server.name == server_name and server.enabled:
                servers.append(
                    MCPServerStatus(
                        name=server.name,
                        transport=server.transport,
                        enabled=server.enabled,
                        state="disconnected",
                        tool_count=server.tool_count,
                        error=error,
                    )
                )
            else:
                servers.append(server)
        self._last_snapshot = summarize_mcp_status(servers)

    def close_all(self) -> None:
        while self._sessions:
            session = self._sessions.pop()
            try:
                session.close()
            except Exception:
                pass

    def _build_session(self, server_config: MCPServerConfig) -> MCPClientSession:
        if server_config.transport == "stdio":
            transport = build_stdio_transport(server_config)
        elif server_config.transport == "http":
            transport = build_http_transport(server_config)
        else:
            raise RuntimeError(f"unsupported MCP transport for runtime: {server_config.transport}")
        session = MCPClientSession(config=server_config, transport=transport)
        self._sessions.append(session)
        return session
