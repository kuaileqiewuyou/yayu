from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
import json
import urllib.request

from core.mcp.config import MCPServerConfig


@dataclass
class MCPHTTPTransport:
    config: MCPServerConfig
    request_opener: Callable[..., Any] = urllib.request.urlopen
    _started: bool = False
    _request_id: int = field(default=0, init=False)

    def start(self) -> None:
        if self._started:
            return
        self._request(
            "initialize",
            {
                "clientInfo": {"name": "yayu", "version": "v1"},
                "capabilities": {},
                "protocolVersion": "2024-11-05",
            },
        )
        self._request("notifications/initialized", {})
        self._started = True

    def list_tools(self) -> list[dict[str, Any]]:
        self.start()
        payload = self._request("tools/list", None)
        return payload.get("tools", [])

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self.start()
        return self._request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        return None

    def _request(self, method: str, params: Any) -> dict[str, Any]:
        self._request_id += 1
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": method,
                "params": params,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json", **self.config.headers}
        request = urllib.request.Request(self.config.url, data=body, headers=headers, method="POST")
        try:
            response = self.request_opener(request, timeout=self.config.timeout)
            payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(f"failed to call MCP HTTP server '{self.config.name}': {exc}") from exc
        if payload.get("error"):
            raise RuntimeError(str(payload["error"]))
        result = payload.get("result")
        return result if isinstance(result, dict) else {}


def build_http_transport(
    config: MCPServerConfig,
    *,
    request_opener: Callable[..., Any] = urllib.request.urlopen,
) -> MCPHTTPTransport:
    return MCPHTTPTransport(config=config, request_opener=request_opener)
