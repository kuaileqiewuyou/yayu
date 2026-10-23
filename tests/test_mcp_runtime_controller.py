from core.mcp.config import MCPServerConfig
from core.mcp.runtime_controller import MCPRuntimeController
from llm.tools.tool_manager import ToolManager


def test_redetect_servers_uses_supplied_configs_closes_sessions_and_updates_snapshot(monkeypatch):
    controller = MCPRuntimeController()
    closed = []
    supplied = [
        MCPServerConfig(name="disabled", transport="stdio", enabled=False),
        MCPServerConfig(name="ready", transport="stdio", command="run"),
    ]

    class Session:
        def list_tools(self):
            return [{"name": "tool"}]

    monkeypatch.setattr(controller, "close_all", lambda: closed.append(True))
    monkeypatch.setattr(controller, "_build_session", lambda config: Session())

    snapshot = controller.redetect_servers(supplied)

    assert closed == [True]
    assert snapshot is controller.last_snapshot
    assert [status.name for status in snapshot.servers] == ["disabled", "ready"]
    assert [status.state for status in snapshot.servers] == ["disabled", "ready"]
    assert snapshot.servers[1].tool_count == 1


class FakeTransport:
    def __init__(self, kind, config):
        self.kind = kind
        self.config = config

    def start(self):
        return None

    def close(self):
        return None

    def list_tools(self):
        return []

    def call_tool(self, name, arguments):
        return {}


class FakeSession:
    def __init__(self, config, tools=None, list_error=None):
        self.config = config
        self._tools = tools or []
        self._list_error = list_error

    def list_tools(self):
        if self._list_error is not None:
            raise self._list_error
        return self._tools

    def close(self):
        return None


class FailingToolSession(FakeSession):
    def __init__(self, config, tools=None, call_error=None):
        super().__init__(config, tools=tools)
        self._call_error = call_error or RuntimeError("bridge closed")

    def call_tool(self, name, arguments):
        raise self._call_error


class FakeManager:
    def __init__(self):
        self._registered = {}

    def register_mcp_tool(self, server_name, tool_name=None, session=None, description="", parameters=None, on_call_failure=None, tool=None):
        if tool is not None:
            tool_name = tool["name"]
            description = tool.get("description", "")
            parameters = tool.get("inputSchema") or {"type": "object", "properties": {}}
        self._registered[f"{server_name}.{tool_name}"] = {
            "session": session,
            "tool_name": tool_name,
            "on_call_failure": on_call_failure,
        }


def test_runtime_controller_builds_http_session(monkeypatch) -> None:
    built = []

    def fake_http_builder(config):
        built.append(("http", config.name, config.url))
        return FakeTransport("http", config)

    def fake_stdio_builder(config):
        built.append(("stdio", config.name, config.command))
        return FakeTransport("stdio", config)

    monkeypatch.setattr("core.mcp.runtime_controller.build_http_transport", fake_http_builder)
    monkeypatch.setattr("core.mcp.runtime_controller.build_stdio_transport", fake_stdio_builder)

    controller = MCPRuntimeController()
    http_config = MCPServerConfig(
        name="remote-api",
        transport="http",
        url="http://127.0.0.1:8080/mcp",
        enabled=True,
    )
    stdio_config = MCPServerConfig(
        name="filesystem",
        transport="stdio",
        command="python",
        args=["server.py"],
        enabled=True,
    )

    http_session = controller._build_session(http_config)
    stdio_session = controller._build_session(stdio_config)

    assert built == [
        ("http", "remote-api", "http://127.0.0.1:8080/mcp"),
        ("stdio", "filesystem", "python"),
    ]
    assert http_session.config.name == "remote-api"
    assert stdio_session.config.name == "filesystem"


def test_register_into_tool_manager_marks_server_ready_after_successful_discovery(monkeypatch) -> None:
    controller = MCPRuntimeController()
    config = MCPServerConfig(name="filesystem", transport="stdio", command="python", enabled=True)
    monkeypatch.setattr(controller, "load_server_configs", lambda: [config])
    monkeypatch.setattr(
        controller,
        "_build_session",
        lambda server_config: FakeSession(
            server_config,
            tools=[{"name": "search_docs", "description": "Search docs", "inputSchema": {"type": "object"}}],
        ),
    )

    snapshot = controller.register_into_tool_manager(FakeManager())

    assert snapshot.state == "ready"
    assert snapshot.servers[0].state == "ready"
    assert snapshot.servers[0].tool_count == 1


def test_register_into_tool_manager_marks_start_failed_when_session_creation_fails(monkeypatch) -> None:
    controller = MCPRuntimeController()
    config = MCPServerConfig(name="filesystem", transport="stdio", command="python", enabled=True)
    monkeypatch.setattr(controller, "load_server_configs", lambda: [config])

    def fail_build(server_config):
        raise RuntimeError("spawn failed")

    monkeypatch.setattr(controller, "_build_session", fail_build)

    snapshot = controller.register_into_tool_manager(FakeManager())

    assert snapshot.state == "failed"
    assert snapshot.servers[0].state == "start_failed"
    assert snapshot.servers[0].error == "spawn failed"


def test_register_into_tool_manager_marks_discover_failed_when_list_tools_fails(monkeypatch) -> None:
    controller = MCPRuntimeController()
    config = MCPServerConfig(name="filesystem", transport="stdio", command="python", enabled=True)
    monkeypatch.setattr(controller, "load_server_configs", lambda: [config])
    monkeypatch.setattr(
        controller,
        "_build_session",
        lambda server_config: FakeSession(server_config, list_error=RuntimeError("discover failed")),
    )

    snapshot = controller.register_into_tool_manager(FakeManager())

    assert snapshot.state == "failed"
    assert snapshot.servers[0].state == "discover_failed"
    assert snapshot.servers[0].error == "discover failed"


def test_runtime_controller_marks_server_disconnected_when_registered_tool_call_fails(monkeypatch) -> None:
    controller = MCPRuntimeController()
    config = MCPServerConfig(name="filesystem", transport="stdio", command="python", enabled=True)
    monkeypatch.setattr(controller, "load_server_configs", lambda: [config])
    monkeypatch.setattr(
        controller,
        "_build_session",
        lambda server_config: FailingToolSession(
            server_config,
            tools=[{"name": "read_file", "description": "Read file", "inputSchema": {"type": "object"}}],
            call_error=RuntimeError("bridge closed"),
        ),
    )

    manager = ToolManager()
    snapshot = controller.register_into_tool_manager(manager)
    assert snapshot.state == "ready"
    assert snapshot.servers[0].state == "ready"

    result = manager.call_tool("filesystem.read_file", {"path": "README.md"})

    assert result.success is False
    assert result.error == "bridge closed"
    updated = controller.get_snapshot()
    assert updated.state == "failed"
    assert updated.servers[0].state == "disconnected"
    assert updated.servers[0].error == "bridge closed"
