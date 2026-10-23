from __future__ import annotations

import json
from typing import Any, TextIO


class MCPStdIOJsonBridge:
    def __init__(self, stdin: TextIO, stdout: TextIO):
        self._stdin = stdin
        self._stdout = stdout
        self._next_id = 1

    def start(self) -> None:
        return None

    def request(self, method: str, params: Any = None) -> Any:
        request_id = self._next_id
        self._next_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        self._stdin.write(json.dumps(payload) + "\n")
        self._stdin.flush()
        line = self._stdout.readline()
        try:
            response = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid JSON response from MCP stdio bridge: {line.strip()}") from exc
        if "error" in response:
            message = response["error"].get("message", "unknown MCP error")
            raise RuntimeError(message)
        return response.get("result")

    def close(self) -> None:
        return None
