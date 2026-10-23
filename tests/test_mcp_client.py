from core.mcp.client import MCPClientSession
from core.mcp.config import MCPServerConfig


class FakeTransport:
    def __init__(self):
        self.started = False
        self.closed = False
        self.list_tools_calls = 0
        self.call_tool_calls = []

    def start(self):
        self.started = True

    def close(self):
        self.closed = True

    def list_tools(self):
        self.list_tools_calls += 1
        return [
            {
                "name": "read_file",
                "description": "Read a file",
                "inputSchema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            }
        ]

    def call_tool(self, name, arguments):
        self.call_tool_calls.append((name, arguments))
        return {"content": [{"type": "text", "text": f"called:{name}"}]}


def test_mcp_client_session_starts_transport_and_lists_tools() -> None:
    transport = FakeTransport()
    config = MCPServerConfig(
        name="filesystem",
        transport="stdio",
        command="python",
        args=["tools/filesystem_server.py"],
        enabled=True,
    )

    session = MCPClientSession(config=config, transport=transport)
    tools = session.list_tools()

    assert transport.started is True
    assert transport.list_tools_calls == 1
    assert tools[0]["name"] == "read_file"


def test_mcp_client_session_calls_tool_through_transport() -> None:
    transport = FakeTransport()
    config = MCPServerConfig(
        name="filesystem",
        transport="stdio",
        command="python",
        args=["tools/filesystem_server.py"],
        enabled=True,
    )

    session = MCPClientSession(config=config, transport=transport)
    result = session.call_tool("read_file", {"path": "README.md"})

    assert transport.started is True
    assert transport.call_tool_calls == [("read_file", {"path": "README.md"})]
    assert result == {"content": [{"type": "text", "text": "called:read_file"}]}


def test_mcp_client_session_close_shuts_down_transport() -> None:
    transport = FakeTransport()
    config = MCPServerConfig(
        name="filesystem",
        transport="stdio",
        command="python",
        args=["tools/filesystem_server.py"],
        enabled=True,
    )

    session = MCPClientSession(config=config, transport=transport)
    session.close()

    assert transport.closed is True
