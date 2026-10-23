from llm.tools.tool_manager import ToolManager
from core.mcp.config import MCPServerConfig
from core.mcp.bootstrap import register_mcp_tools


class FakeMCPSession:
    def __init__(self, tools):
        self._tools = tools
        self.calls = []

    def list_tools(self):
        self.calls.append("list_tools")
        return self._tools

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {"content": [{"type": "text", "text": f"called:{name}"}]}


def test_register_mcp_tools_keeps_tool_manager_unchanged_when_no_servers() -> None:
    manager = ToolManager()

    snapshot = register_mcp_tools(
        tool_manager=manager,
        server_configs=[],
        session_factory=lambda config: None,
    )

    assert manager.list_tools() == []
    assert snapshot.state == "disabled"
    assert snapshot.servers == []


def test_register_mcp_tools_registers_tools_from_server_sessions() -> None:
    manager = ToolManager()
    configs = [
        MCPServerConfig(
            name="filesystem",
            transport="stdio",
            command="python",
            args=["tools/filesystem_server.py"],
            enabled=True,
        )
    ]

    session = FakeMCPSession(
        [
            {
                "name": "read_file",
                "description": "Read a file from disk",
                "inputSchema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            }
        ]
    )

    snapshot = register_mcp_tools(
        tool_manager=manager,
        server_configs=configs,
        session_factory=lambda config: session,
    )

    assert session.calls == ["list_tools"]
    assert manager.list_tools() == ["filesystem.read_file"]
    definitions = manager.get_tool_definitions()
    assert definitions[0]["function"]["name"] == "filesystem.read_file"
    assert snapshot.state == "ready"
    assert snapshot.servers[0].tool_count == 1


def test_register_mcp_tools_reports_partial_failure() -> None:
    manager = ToolManager()
    configs = [
        MCPServerConfig(name="ok", transport="stdio", command="python", args=["ok.py"]),
        MCPServerConfig(name="bad", transport="stdio", command="python", args=["bad.py"]),
    ]

    session = FakeMCPSession([{"name": "ping", "description": "", "inputSchema": {"type": "object", "properties": {}}}])

    def session_factory(config):
        if config.name == "bad":
            raise RuntimeError("boom")
        return session

    snapshot = register_mcp_tools(
        tool_manager=manager,
        server_configs=configs,
        session_factory=session_factory,
    )

    assert snapshot.state == "partial"
    assert len(snapshot.servers) == 2
    failed = [item for item in snapshot.servers if item.state == "failed"][0]
    assert failed.name == "bad"
    assert "boom" in failed.error


def test_register_mcp_tools_registers_tools_from_http_server_sessions() -> None:
    manager = ToolManager()
    configs = [
        MCPServerConfig(
            name="remote-api",
            transport="http",
            url="http://127.0.0.1:8080/mcp",
            enabled=True,
        )
    ]

    session = FakeMCPSession(
        [
            {
                "name": "search_docs",
                "description": "Search remote MCP docs",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ]
    )

    snapshot = register_mcp_tools(
        tool_manager=manager,
        server_configs=configs,
        session_factory=lambda config: session,
    )

    assert session.calls == ["list_tools"]
    assert manager.list_tools() == ["remote-api.search_docs"]
    definitions = manager.get_tool_definitions()
    assert definitions[0]["function"]["name"] == "remote-api.search_docs"
    assert snapshot.state == "ready"
    assert snapshot.servers[0].transport == "http"
    assert snapshot.servers[0].tool_count == 1
