from pathlib import Path

from config.config_manager import ConfigManager
from config.schema import AppConfig
from core.mcp.config import MCPServerConfig


def test_app_config_includes_mcp_servers_default() -> None:
    config = AppConfig()
    assert config.mcp_servers == []


def test_config_manager_loads_mcp_servers_from_yaml(tmp_path: Path) -> None:
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
          - name: filesystem
            transport: stdio
            command: python
            args:
              - tools/filesystem_server.py
            enabled: true
        """,
        encoding="utf-8",
    )

    original_api = ConfigManager._API_CONFIG_PATH
    original_api_local = ConfigManager._API_LOCAL_CONFIG_PATH
    original_characters = ConfigManager._CHARACTERS_CONFIG_PATH
    original_system = ConfigManager._SYSTEM_CONFIG_PATH
    original_background = ConfigManager._BACKGROUND_CONFIG_PATH
    original_mcp = getattr(ConfigManager, "_MCP_CONFIG_PATH", Path("data/config/mcp.yaml"))
    ConfigManager.reset()
    try:
        ConfigManager._API_CONFIG_PATH = config_root / "api.yaml"
        ConfigManager._API_LOCAL_CONFIG_PATH = config_root / "api.local.yaml"
        ConfigManager._CHARACTERS_CONFIG_PATH = config_root / "characters.yaml"
        ConfigManager._SYSTEM_CONFIG_PATH = config_root / "system_config.yaml"
        ConfigManager._BACKGROUND_CONFIG_PATH = config_root / "background.yaml"
        ConfigManager._MCP_CONFIG_PATH = config_root / "mcp.yaml"

        manager = ConfigManager()

        assert len(manager.config.mcp_servers) == 1
        assert len(manager.mcp_servers) == 1
        server = manager.config.mcp_servers[0]
        assert server.name == "filesystem"
        assert server.transport == "stdio"
        assert server.command == "python"
        assert server.args == ["tools/filesystem_server.py"]
        assert server.env == {}
        assert server.url == ""
        assert server.headers == {}
        assert server.timeout == 120
        assert server.connect_timeout == 60
        assert server.enabled is True
    finally:
        ConfigManager._API_CONFIG_PATH = original_api
        ConfigManager._API_LOCAL_CONFIG_PATH = original_api_local
        ConfigManager._CHARACTERS_CONFIG_PATH = original_characters
        ConfigManager._SYSTEM_CONFIG_PATH = original_system
        ConfigManager._BACKGROUND_CONFIG_PATH = original_background
        ConfigManager._MCP_CONFIG_PATH = original_mcp
        ConfigManager.reset()


def test_config_manager_loads_http_mcp_server_from_yaml(tmp_path: Path) -> None:
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
            url: https://example.test/mcp
            headers:
              Authorization: Bearer token
            timeout: 180
            connect_timeout: 30
            enabled: true
        """,
        encoding="utf-8",
    )

    original_api = ConfigManager._API_CONFIG_PATH
    original_api_local = ConfigManager._API_LOCAL_CONFIG_PATH
    original_characters = ConfigManager._CHARACTERS_CONFIG_PATH
    original_system = ConfigManager._SYSTEM_CONFIG_PATH
    original_background = ConfigManager._BACKGROUND_CONFIG_PATH
    original_mcp = getattr(ConfigManager, "_MCP_CONFIG_PATH", Path("data/config/mcp.yaml"))
    ConfigManager.reset()
    try:
        ConfigManager._API_CONFIG_PATH = config_root / "api.yaml"
        ConfigManager._API_LOCAL_CONFIG_PATH = config_root / "api.local.yaml"
        ConfigManager._CHARACTERS_CONFIG_PATH = config_root / "characters.yaml"
        ConfigManager._SYSTEM_CONFIG_PATH = config_root / "system_config.yaml"
        ConfigManager._BACKGROUND_CONFIG_PATH = config_root / "background.yaml"
        ConfigManager._MCP_CONFIG_PATH = config_root / "mcp.yaml"

        manager = ConfigManager()

        assert len(manager.mcp_servers) == 1
        server = manager.mcp_servers[0]
        assert server.name == "remote-api"
        assert server.transport == "http"
        assert server.command == ""
        assert server.args == []
        assert server.url == "https://example.test/mcp"
        assert server.headers == {"Authorization": "Bearer token"}
        assert server.timeout == 180
        assert server.connect_timeout == 30
    finally:
        ConfigManager._API_CONFIG_PATH = original_api
        ConfigManager._API_LOCAL_CONFIG_PATH = original_api_local
        ConfigManager._CHARACTERS_CONFIG_PATH = original_characters
        ConfigManager._SYSTEM_CONFIG_PATH = original_system
        ConfigManager._BACKGROUND_CONFIG_PATH = original_background
        ConfigManager._MCP_CONFIG_PATH = original_mcp
        ConfigManager.reset()


def test_config_manager_can_save_mcp_servers(tmp_path: Path) -> None:
    config_root = tmp_path / "data" / "config"
    config_root.mkdir(parents=True)
    (config_root / "api.yaml").write_text("{}\n", encoding="utf-8")
    (config_root / "api.local.yaml").write_text("{}\n", encoding="utf-8")
    (config_root / "characters.yaml").write_text("[]\n", encoding="utf-8")
    (config_root / "system_config.yaml").write_text("{}\n", encoding="utf-8")
    (config_root / "background.yaml").write_text("[]\n", encoding="utf-8")
    (config_root / "mcp.yaml").write_text("mcp_servers: []\n", encoding="utf-8")

    original_api = ConfigManager._API_CONFIG_PATH
    original_api_local = ConfigManager._API_LOCAL_CONFIG_PATH
    original_characters = ConfigManager._CHARACTERS_CONFIG_PATH
    original_system = ConfigManager._SYSTEM_CONFIG_PATH
    original_background = ConfigManager._BACKGROUND_CONFIG_PATH
    original_mcp = getattr(ConfigManager, "_MCP_CONFIG_PATH", Path("data/config/mcp.yaml"))
    ConfigManager.reset()
    try:
        ConfigManager._API_CONFIG_PATH = config_root / "api.yaml"
        ConfigManager._API_LOCAL_CONFIG_PATH = config_root / "api.local.yaml"
        ConfigManager._CHARACTERS_CONFIG_PATH = config_root / "characters.yaml"
        ConfigManager._SYSTEM_CONFIG_PATH = config_root / "system_config.yaml"
        ConfigManager._BACKGROUND_CONFIG_PATH = config_root / "background.yaml"
        ConfigManager._MCP_CONFIG_PATH = config_root / "mcp.yaml"

        manager = ConfigManager()
        manager.set_mcp_servers(
            [
                MCPServerConfig(
                    name="filesystem",
                    transport="stdio",
                    command="python",
                    args=["tools/filesystem_server.py"],
                    env={"DEBUG": "1"},
                    timeout=45,
                    connect_timeout=10,
                )
            ]
        )
        manager.save_mcp_servers()

        saved = (config_root / "mcp.yaml").read_text(encoding="utf-8")
        assert "name: filesystem" in saved
        assert "transport: stdio" in saved
        assert "command: python" in saved
        assert "DEBUG: '1'" in saved or "DEBUG: \"1\"" in saved or "DEBUG: 1" in saved
    finally:
        ConfigManager._API_CONFIG_PATH = original_api
        ConfigManager._API_LOCAL_CONFIG_PATH = original_api_local
        ConfigManager._CHARACTERS_CONFIG_PATH = original_characters
        ConfigManager._SYSTEM_CONFIG_PATH = original_system
        ConfigManager._BACKGROUND_CONFIG_PATH = original_background
        ConfigManager._MCP_CONFIG_PATH = original_mcp
        ConfigManager.reset()
