import json
from io import StringIO

from core.mcp.bridge_stdio import MCPStdIOJsonBridge


class FakeStreamPair:
    def __init__(self, response_payload):
        self.stdin = StringIO()
        self.stdout = StringIO(json.dumps(response_payload) + "\n")


def test_mcp_stdio_json_bridge_request_writes_jsonrpc_message_and_reads_response() -> None:
    pair = FakeStreamPair(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"tools": [{"name": "read_file"}]},
        }
    )
    bridge = MCPStdIOJsonBridge(pair.stdin, pair.stdout)

    result = bridge.request("tools/list", None)

    pair.stdin.seek(0)
    sent = json.loads(pair.stdin.read())
    assert sent == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": None,
    }
    assert result == {"tools": [{"name": "read_file"}]}


def test_mcp_stdio_json_bridge_request_raises_on_error_response() -> None:
    pair = FakeStreamPair(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32000, "message": "tool failed"},
        }
    )
    bridge = MCPStdIOJsonBridge(pair.stdin, pair.stdout)

    try:
        bridge.request("tools/call", {"name": "read_file"})
    except RuntimeError as exc:
        assert "tool failed" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for MCP error response")


def test_mcp_stdio_json_bridge_increments_request_id_across_multiple_calls() -> None:
    stdin = StringIO()
    stdout = StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": 1}}) + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"ok": 2}}) + "\n"
    )
    bridge = MCPStdIOJsonBridge(stdin, stdout)

    first = bridge.request("tools/list", None)
    second = bridge.request("tools/call", {"name": "ping"})

    stdin.seek(0)
    sent_lines = [json.loads(line) for line in stdin.getvalue().splitlines() if line.strip()]
    assert sent_lines == [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": None},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "ping"}},
    ]
    assert first == {"ok": 1}
    assert second == {"ok": 2}


def test_mcp_stdio_json_bridge_raises_readable_error_on_invalid_json_response() -> None:
    stdin = StringIO()
    stdout = StringIO("not-json\n")
    bridge = MCPStdIOJsonBridge(stdin, stdout)

    try:
        bridge.request("tools/list", None)
    except RuntimeError as exc:
        assert "invalid JSON" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for invalid JSON response")
