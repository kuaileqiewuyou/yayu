from core.mcp.transport_stdio import MCPStdioTransport
from core.mcp.config import MCPServerConfig


class FakeProcess:
    def __init__(self):
        self.terminated = False
        self.terminate_calls = 0

    def terminate(self):
        self.terminated = True
        self.terminate_calls += 1


class FakeStdIOBridge:
    def __init__(self):
        self.started = False
        self.closed = False
        self.close_calls = 0
        self.requests = []

    def start(self):
        self.started = True

    def request(self, method, params=None):
        self.requests.append((method, params))
        if method == "tools/list":
            return {"tools": [{"name": "read_file", "description": "Read a file", "inputSchema": {"type": "object", "properties": {}}}]}
        if method == "tools/call":
            return {"content": [{"type": "text", "text": "called"}]}
        return {}

    def close(self):
        self.closed = True
        self.close_calls += 1


def test_mcp_stdio_transport_starts_process_and_initializes_bridge() -> None:
    config = MCPServerConfig(
        name="filesystem",
        transport="stdio",
        command="python",
        args=["tools/filesystem_server.py"],
        enabled=True,
    )
    bridge = FakeStdIOBridge()
    process = FakeProcess()
    transport = MCPStdioTransport(config=config, process=process, bridge=bridge)

    transport.start()

    assert bridge.started is True
    assert bridge.requests[0] == (
        "initialize",
        {
            "clientInfo": {"name": "yayu", "version": "v1"},
            "capabilities": {},
            "protocolVersion": "2024-11-05",
        },
    )
    assert bridge.requests[1] == ("notifications/initialized", {})


def test_mcp_stdio_transport_lists_tools_via_bridge_request() -> None:
    config = MCPServerConfig(
        name="filesystem",
        transport="stdio",
        command="python",
        args=["tools/filesystem_server.py"],
        enabled=True,
    )
    bridge = FakeStdIOBridge()
    process = FakeProcess()
    transport = MCPStdioTransport(config=config, process=process, bridge=bridge)

    transport.start()
    tools = transport.list_tools()

    assert bridge.requests[0][0] == "initialize"
    assert bridge.requests[1] == ("notifications/initialized", {})
    assert bridge.requests[2] == ("tools/list", None)
    assert tools[0]["name"] == "read_file"


def test_mcp_stdio_transport_calls_tool_via_bridge_request() -> None:
    config = MCPServerConfig(
        name="filesystem",
        transport="stdio",
        command="python",
        args=["tools/filesystem_server.py"],
        enabled=True,
    )
    bridge = FakeStdIOBridge()
    process = FakeProcess()
    transport = MCPStdioTransport(config=config, process=process, bridge=bridge)

    transport.start()
    result = transport.call_tool("read_file", {"path": "README.md"})

    assert bridge.requests[-1] == ("tools/call", {"name": "read_file", "arguments": {"path": "README.md"}})
    assert result == {"content": [{"type": "text", "text": "called"}]}


def test_mcp_stdio_transport_close_shuts_down_bridge_and_process() -> None:
    config = MCPServerConfig(
        name="filesystem",
        transport="stdio",
        command="python",
        args=["tools/filesystem_server.py"],
        enabled=True,
    )
    bridge = FakeStdIOBridge()
    process = FakeProcess()
    transport = MCPStdioTransport(config=config, process=process, bridge=bridge)

    transport.close()
    transport.close()

    assert bridge.closed is True
    assert process.terminated is True
    assert bridge.close_calls == 1
    assert process.terminate_calls == 1
