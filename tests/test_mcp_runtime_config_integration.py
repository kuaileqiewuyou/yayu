from pathlib import Path

from config.config_manager import ConfigManager
from core.mcp.runtime_controller import MCPRuntimeController
from llm.tools.tool_manager import ToolManager


class FakeSession:
    def __init__(self, config):
        self.config = config
        self.calls = []

    def list_tools(self):
        self.calls.append("list_tools")
        return [
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

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {"content": [{"type": "text", "text": f"called:{name}"}]}

    def close(self):
        self.calls.append("close")


def test_runtime_controller_registers_http_server_from_yaml(tmp_path: Path, monkeypatch) -> None:
    config_root = tmp_path / "data" / "config"
    config_root.mkdir(parents=True)
    (config_root / "api.yaml").write_text("{}\n", encoding="utf-8")
    (config_root / "api.local.yaml").write_text("{}\n", encoding="utf-8")
    (config_root / "characters.yaml").write_text("[]\n", encoding="utf-8")
    (config_root / "system_config.yaml").write_text("{}\n", encoding="utf-8")
    (config_root / "background.yaml").write_text("[]\n", encoding="utf-8")
    (config_root / "mcp.yaml").write_text(
        """
        mcp_servers:
          - name: remote-api
            transport: http
            url: http://127.0.0.1:8080/mcp
            headers:
              Authorization: Bearer token
            enabled: true
        """,
        encoding="utf-8",
    )

    original_api = ConfigManager._API_CONFIG_PATH
    original_api_local = ConfigManager._API_LOCAL_CONFIG_PATH
    original_characters = ConfigManager._CHARACTERS_CONFIG_PATH
    original_system = ConfigManager._SYSTEM_CONFIG_PATH
    original_background = ConfigManager._BACKGROUND_CONFIG_PATH
    original_mcp = ConfigManager._MCP_CONFIG_PATH
    ConfigManager.reset()
    try:
        ConfigManager._API_CONFIG_PATH = config_root / "api.yaml"
        ConfigManager._API_LOCAL_CONFIG_PATH = config_root / "api.local.yaml"
        ConfigManager._CHARACTERS_CONFIG_PATH = config_root / "characters.yaml"
        ConfigManager._SYSTEM_CONFIG_PATH = config_root / "system_config.yaml"
        ConfigManager._BACKGROUND_CONFIG_PATH = config_root / "background.yaml"
        ConfigManager._MCP_CONFIG_PATH = config_root / "mcp.yaml"

        sessions = []

        def fake_build_session(self, server_config):
            session = FakeSession(server_config)
            sessions.append(session)
            return session

        monkeypatch.setattr(MCPRuntimeController, "_build_session", fake_build_session)

        manager = ToolManager()
        controller = MCPRuntimeController(config_path=config_root / "mcp.yaml")
        snapshot = controller.register_into_tool_manager(manager)

        assert len(sessions) == 1
        assert sessions[0].config.name == "remote-api"
        assert sessions[0].config.transport == "http"
        assert sessions[0].config.url == "http://127.0.0.1:8080/mcp"
        assert manager.list_tools() == ["remote-api.search_docs"]
        definitions = manager.get_tool_definitions()
        assert definitions == [
            {
                "type": "function",
                "function": {
                    "name": "remote-api.search_docs",
                    "description": "Search remote MCP docs",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            }
        ]
        assert snapshot.state == "ready"
        assert snapshot.servers[0].transport == "http"
        assert snapshot.servers[0].tool_count == 1
    finally:
        ConfigManager._API_CONFIG_PATH = original_api
        ConfigManager._API_LOCAL_CONFIG_PATH = original_api_local
        ConfigManager._CHARACTERS_CONFIG_PATH = original_characters
        ConfigManager._SYSTEM_CONFIG_PATH = original_system
        ConfigManager._BACKGROUND_CONFIG_PATH = original_background
        ConfigManager._MCP_CONFIG_PATH = original_mcp
        ConfigManager.reset()


def test_runtime_controller_registered_http_tool_calls_through_tool_manager(tmp_path: Path, monkeypatch) -> None:
    config_root = tmp_path / "data" / "config"
    config_root.mkdir(parents=True)
    (config_root / "api.yaml").write_text("{}\n", encoding="utf-8")
    (config_root / "api.local.yaml").write_text("{}\n", encoding="utf-8")
    (config_root / "characters.yaml").write_text("[]\n", encoding="utf-8")
    (config_root / "system_config.yaml").write_text("{}\n", encoding="utf-8")
    (config_root / "background.yaml").write_text("[]\n", encoding="utf-8")
    (config_root / "mcp.yaml").write_text(
        """
        mcp_servers:
          - name: remote-api
            transport: http
            url: http://127.0.0.1:8080/mcp
            enabled: true
        """,
        encoding="utf-8",
    )

    original_api = ConfigManager._API_CONFIG_PATH
    original_api_local = ConfigManager._API_LOCAL_CONFIG_PATH
    original_characters = ConfigManager._CHARACTERS_CONFIG_PATH
    original_system = ConfigManager._SYSTEM_CONFIG_PATH
    original_background = ConfigManager._BACKGROUND_CONFIG_PATH
    original_mcp = ConfigManager._MCP_CONFIG_PATH
    ConfigManager.reset()
    try:
        ConfigManager._API_CONFIG_PATH = config_root / "api.yaml"
        ConfigManager._API_LOCAL_CONFIG_PATH = config_root / "api.local.yaml"
        ConfigManager._CHARACTERS_CONFIG_PATH = config_root / "characters.yaml"
        ConfigManager._SYSTEM_CONFIG_PATH = config_root / "system_config.yaml"
        ConfigManager._BACKGROUND_CONFIG_PATH = config_root / "background.yaml"
        ConfigManager._MCP_CONFIG_PATH = config_root / "mcp.yaml"

        sessions = []

        def fake_build_session(self, server_config):
            session = FakeSession(server_config)
            sessions.append(session)
            return session

        monkeypatch.setattr(MCPRuntimeController, "_build_session", fake_build_session)

        manager = ToolManager()
        controller = MCPRuntimeController(config_path=config_root / "mcp.yaml")
        controller.register_into_tool_manager(manager)

        result = manager.call_tool("remote-api.search_docs", {"query": "MCP auth"})

        assert len(sessions) == 1
        assert sessions[0].calls == ["list_tools", ("search_docs", {"query": "MCP auth"})]
        assert result.success is True
        assert result.error is None
        assert result.value == {"content": [{"type": "text", "text": "called:search_docs"}]}
    finally:
        ConfigManager._API_CONFIG_PATH = original_api
        ConfigManager._API_LOCAL_CONFIG_PATH = original_api_local
        ConfigManager._CHARACTERS_CONFIG_PATH = original_characters
        ConfigManager._SYSTEM_CONFIG_PATH = original_system
        ConfigManager._BACKGROUND_CONFIG_PATH = original_background
        ConfigManager._MCP_CONFIG_PATH = original_mcp
        ConfigManager.reset()
