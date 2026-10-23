from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from core.mcp.config import MCPServerConfig


class MCPTransport(Protocol):
    def start(self) -> None: ...
    def close(self) -> None: ...
    def list_tools(self) -> list[dict[str, Any]]: ...
    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


@dataclass
class MCPClientSession:
    config: MCPServerConfig
    transport: MCPTransport
    _started: bool = False

    def _ensure_started(self) -> None:
        if not self._started:
            self.transport.start()
            self._started = True

    def list_tools(self) -> list[dict[str, Any]]:
        self._ensure_started()
        return self.transport.list_tools()

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self._ensure_started()
        return self.transport.call_tool(name, arguments)

    def close(self) -> None:
        self.transport.close()
