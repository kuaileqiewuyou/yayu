from pathlib import Path

import pytest

from core.mcp.config import MCPServerConfig, load_mcp_server_configs


def test_load_mcp_server_configs_returns_empty_for_missing_file(tmp_path: Path) -> None:
    configs = load_mcp_server_configs(tmp_path / "missing-mcp.yaml")
    assert configs == []


def test_load_mcp_server_configs_preserves_disabled_server_drafts(tmp_path: Path) -> None:
    config_path = tmp_path / "mcp.yaml"
    config_path.write_text(
        """
        mcp_servers:
          - name: disabled-server
            transport: stdio
            command: ""
            args: []
            enabled: false
        """,
        encoding="utf-8",
    )

    configs = load_mcp_server_configs(config_path)
    assert configs == [
        MCPServerConfig(
            name="disabled-server",
            transport="stdio",
            command="",
            args=[],
            enabled=False,
        )
    ]


def test_load_mcp_server_configs_reads_enabled_stdio_server(tmp_path: Path) -> None:
    config_path = tmp_path / "mcp.yaml"
    config_path.write_text(
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

    configs = load_mcp_server_configs(config_path)

    assert configs == [
        MCPServerConfig(
            name="filesystem",
            transport="stdio",
            command="python",
            args=["tools/filesystem_server.py"],
            enabled=True,
        )
    ]


def test_load_mcp_server_configs_rejects_missing_required_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "mcp.yaml"
    config_path.write_text(
        """
        mcp_servers:
          - name: broken
            transport: stdio
            enabled: true
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="command"):
        load_mcp_server_configs(config_path)
