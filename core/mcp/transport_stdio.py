from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
import subprocess

from core.mcp.bridge_stdio import MCPStdIOJsonBridge
from core.mcp.config import MCPServerConfig


@dataclass
class MCPStdioTransport:
    config: MCPServerConfig
    process: Any
    bridge: Any
    _started: bool = False
    _closed: bool = False

    def start(self) -> None:
        if not self._started:
            self.bridge.start()
            self.bridge.request(
                "initialize",
                {
                    "clientInfo": {"name": "yayu", "version": "v1"},
                    "capabilities": {},
                    "protocolVersion": "2024-11-05",
                },
            )
            self.bridge.request("notifications/initialized", {})
            self._started = True

    def list_tools(self) -> list[dict[str, Any]]:
        self.start()
        payload = self.bridge.request("tools/list", None)
        return payload.get("tools", [])

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self.start()
        return self.bridge.request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        if self._closed:
            return
        self.bridge.close()
        self.process.terminate()
        self._closed = True


def _default_bridge_factory(process: Any) -> Any:
    return MCPStdIOJsonBridge(process.stdin, process.stdout)


def build_stdio_transport(
    config: MCPServerConfig,
    *,
    popen_factory: Callable[..., Any] = subprocess.Popen,
    bridge_factory: Callable[[Any], Any] = _default_bridge_factory,
) -> MCPStdioTransport:
    command = [config.command, *config.args]
    try:
        process = popen_factory(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError(f"failed to start MCP stdio server '{config.name}': {exc}") from exc
    bridge = bridge_factory(process)
    return MCPStdioTransport(config=config, process=process, bridge=bridge)
