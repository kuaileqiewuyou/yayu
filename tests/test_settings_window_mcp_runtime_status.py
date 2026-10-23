import pytest
from PySide6.QtWidgets import QApplication

from core.mcp.status import MCPServerStatus, MCPStatusSnapshot
from ui.settings_ui.window import SettingsWindow


@pytest.fixture
def make_settings_window_with_app(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    windows = []

    def _make():
        window = SettingsWindow()
        windows.append(window)
        return window

    yield _make

    for window in windows:
        window.close()
        window.deleteLater()
    app.processEvents()


def test_settings_window_renders_top_level_mcp_runtime_summary_from_snapshot(make_settings_window_with_app):
    window = make_settings_window_with_app()
    snapshot = MCPStatusSnapshot(
        state="partial",
        servers=[
            MCPServerStatus(name="filesystem", transport="stdio", enabled=True, state="ready", tool_count=2),
            MCPServerStatus(name="remote-api", transport="http", enabled=True, state="discover_failed", error="auth failed"),
        ],
    )

    window.refresh_mcp_status(snapshot)

    assert "MCP 状态：partial" in window.mcp_summary_label.text()
    assert "成功 1 个，失败 1 个" in window.mcp_summary_label.text()


def test_settings_window_renders_per_server_transport_tool_count_and_error(make_settings_window_with_app):
    window = make_settings_window_with_app()
    snapshot = MCPStatusSnapshot(
        state="failed",
        servers=[
            MCPServerStatus(
                name="filesystem",
                transport="stdio",
                enabled=True,
                state="disconnected",
                tool_count=2,
                error="bridge closed",
            )
        ],
    )

    window.refresh_mcp_status(snapshot)

    assert window.mcp_server_list.count() == 1
    item_text = window.mcp_server_list.item(0).text()
    assert "filesystem" in item_text
    assert "disconnected" in item_text
    assert "tools=2" in item_text
    assert "bridge closed" in window._mcp_tab_parts.detail_label.text()
