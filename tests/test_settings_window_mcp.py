import json
import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMessageBox

from config.config_manager import ConfigManager
from core.mcp.runtime_controller import MCPRuntimeController
from core.mcp.status import MCPServerStatus, MCPStatusSnapshot
from ui.settings_ui.window import SettingsWindow


@pytest.fixture
def make_settings_window_with_app(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    windows = []

    def _make():
        ConfigManager.reset()
        window = SettingsWindow()
        windows.append(window)
        return window

    yield _make

    for window in windows:
        window.close()
        window.deleteLater()
    ConfigManager.reset()
    app.processEvents()


def test_settings_window_has_mcp_tab_widgets(make_settings_window_with_app):
    window = make_settings_window_with_app()

    assert window.mcp_redetect_button.text() == "重新检测 MCP"
    assert window.mcp_add_server_button.text() == "新增 MCP Server"
    assert window.mcp_remove_server_button.text() == "删除选中 MCP Server"
    assert window.mcp_test_server_button.text() == "测试选中 MCP Server"
    assert window.mcp_summary_label.text() == "MCP 状态：未检测"
    assert window.mcp_server_list.count() == 0
    assert window.mcp_save_server_button.text() == "更新服务器草稿"
    assert '"command": ""' in window.mcp_json_edit.placeholderText()


def test_settings_window_refreshes_mcp_status_summary_and_detail(make_settings_window_with_app):
    window = make_settings_window_with_app()
    controller = MCPRuntimeController()
    controller._last_snapshot = MCPStatusSnapshot(
        state="partial",
        servers=[
            MCPServerStatus(
                name="filesystem",
                transport="stdio",
                enabled=True,
                state="ready",
                tool_count=2,
            ),
            MCPServerStatus(
                name="remote-api",
                transport="http",
                enabled=True,
                state="discover_failed",
                error="auth failed",
            ),
        ],
    )
    window.set_mcp_runtime_controller(controller)
    window.refresh_mcp_status(controller.last_snapshot)

    assert "MCP 状态：partial" in window.mcp_summary_label.text()
    assert "成功 1 个，失败 1 个" in window.mcp_summary_label.text()
    assert window.mcp_server_list.count() == 2
    assert "filesystem" in window.mcp_server_list.item(0).text()
    assert "名称：filesystem" in window._mcp_tab_parts.detail_label.text()


def test_settings_window_renders_disconnected_runtime_status_detail(make_settings_window_with_app):
    window = make_settings_window_with_app()
    controller = MCPRuntimeController()
    controller._last_snapshot = MCPStatusSnapshot(
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
    window.set_mcp_runtime_controller(controller)
    window.refresh_mcp_status(controller.last_snapshot)

    assert "MCP 状态：failed" in window.mcp_summary_label.text()
    assert window.mcp_server_list.count() == 1
    assert "disconnected" in window.mcp_server_list.item(0).text()
    assert "tools=2" in window.mcp_server_list.item(0).text()
    assert "bridge closed" in window._mcp_tab_parts.detail_label.text()


def test_settings_window_renders_discovered_tools_in_detail(make_settings_window_with_app):
    window = make_settings_window_with_app()
    controller = MCPRuntimeController()
    controller._last_snapshot = MCPStatusSnapshot(
        state="ready",
        servers=[
            MCPServerStatus(
                name="filesystem",
                transport="stdio",
                enabled=True,
                state="ready",
                tool_count=2,
                discovered_tools=["read_file", "write_file"],
                discovered_tool_descriptions={
                    "read_file": "Read a file from disk",
                    "write_file": "Write a file to disk",
                },
            )
        ],
    )
    window.set_mcp_runtime_controller(controller)
    window.refresh_mcp_status(controller.last_snapshot)

    detail_text = window._mcp_tab_parts.detail_label.text()
    assert "发现工具数：2" in detail_text
    assert "read_file" in detail_text
    assert "write_file" in detail_text
    assert "Read a file from disk" in detail_text
    assert "Write a file to disk" in detail_text


def test_settings_window_http_server_detail_mentions_url(make_settings_window_with_app):
    window = make_settings_window_with_app()
    window._add_mcp_server()
    window._mcp_selected_row = 0
    window.mcp_name_edit.setText("remote-api")
    window.mcp_transport_combo.setCurrentText("http")
    window.mcp_enabled_check.setChecked(True)
    window.mcp_http_url_edit.setText("http://127.0.0.1:8080/mcp")
    window.mcp_json_edit.setPlainText(json.dumps({
        "headers": {"Authorization": "Bearer test-token"},
        "enabled": True,
    }, ensure_ascii=False, indent=2))
    window._update_selected_mcp_server_from_form()
    window._show_selected_mcp_server_detail(0)

    detail_text = window._mcp_tab_parts.detail_label.text()
    editor_payload = window.mcp_json_edit.toPlainText()
    assert "Transport：http" in detail_text
    assert '"url": "http://127.0.0.1:8080/mcp"' in editor_payload


def test_settings_window_exposes_basic_http_fields_without_relying_only_on_raw_json(make_settings_window_with_app):
    window = make_settings_window_with_app()

    assert hasattr(window, "mcp_transport_combo")
    assert hasattr(window, "mcp_http_url_edit")
    assert hasattr(window, "mcp_enabled_check")


def test_settings_window_http_common_fields_sync_into_json_payload(make_settings_window_with_app):
    window = make_settings_window_with_app()
    window._add_mcp_server()
    window._mcp_selected_row = 0
    window.mcp_name_edit.setText("remote-api")
    window.mcp_transport_combo.setCurrentText("http")
    window.mcp_enabled_check.setChecked(True)
    window.mcp_http_url_edit.setText("http://127.0.0.1:8080/mcp")
    window.mcp_json_edit.setPlainText(json.dumps({
        "headers": {"Authorization": "Bearer test-token"}
    }, ensure_ascii=False, indent=2))

    window._update_selected_mcp_server_from_form()
    window._show_selected_mcp_server_detail(0)

    assert '"url": "http://127.0.0.1:8080/mcp"' in window.mcp_json_edit.toPlainText()


def test_settings_window_http_form_edits_refresh_advanced_json_payload(make_settings_window_with_app):
    window = make_settings_window_with_app()
    window._add_mcp_server()
    window._mcp_selected_row = 0
    window.mcp_transport_combo.setCurrentText("http")
    window.mcp_http_url_edit.setText("http://127.0.0.1:9000/mcp")
    window.mcp_enabled_check.setChecked(False)
    window.mcp_json_edit.setPlainText("{}")

    window._update_selected_mcp_server_from_form()
    window._show_selected_mcp_server_detail(0)

    payload = json.loads(window.mcp_json_edit.toPlainText())
    assert payload["url"] == "http://127.0.0.1:9000/mcp"
    assert payload["enabled"] is False


def test_settings_window_renders_disabled_server_without_counting_it_as_failure(make_settings_window_with_app):
    window = make_settings_window_with_app()
    controller = MCPRuntimeController()
    controller._last_snapshot = MCPStatusSnapshot(
        state="disabled",
        servers=[
            MCPServerStatus(
                name="filesystem",
                transport="stdio",
                enabled=False,
                state="disabled",
            )
        ],
    )
    window.set_mcp_runtime_controller(controller)
    window.refresh_mcp_status(controller.last_snapshot)

    assert "MCP 状态：disabled" in window.mcp_summary_label.text()
    assert "成功 0 个，失败 1 个" not in window.mcp_summary_label.text()
    assert window.mcp_server_list.count() == 1
    assert "disabled" in window.mcp_server_list.item(0).text()
    assert "启用：否" in window._mcp_tab_parts.detail_label.text()


def test_settings_window_redetect_mcp_requires_controller(make_settings_window_with_app):
    window = make_settings_window_with_app()

    window._redetect_mcp()

    assert "MCP 控制器尚未初始化" in window.save_status_label.text()


def test_settings_window_redetect_mcp_uses_current_validated_server_draft(make_settings_window_with_app):
    window = make_settings_window_with_app()
    window._add_mcp_server()
    window.mcp_name_edit.setText("current-draft")
    window.mcp_transport_combo.setCurrentText("stdio")
    window.mcp_enabled_check.setChecked(True)
    window.mcp_json_edit.setPlainText(json.dumps({"command": "uvx", "args": ["server"]}))

    class FakeController:
        def __init__(self):
            self.received_servers = None
            self._last_snapshot = MCPStatusSnapshot(state="disabled", servers=[])

        @property
        def last_snapshot(self):
            return self._last_snapshot

        def redetect_servers(self, servers):
            self.received_servers = list(servers)
            self._last_snapshot = MCPStatusSnapshot(state="ready", servers=[])
            return self._last_snapshot

    controller = FakeController()
    window.set_mcp_runtime_controller(controller)

    window._redetect_mcp()

    assert len(controller.received_servers) == 1
    assert controller.received_servers[0].name == "current-draft"
    assert controller.received_servers[0].command == "uvx"
    assert controller.received_servers[0].args == ["server"]
    assert "当前状态：ready" in window.save_status_label.text()


def test_settings_window_redetect_mcp_reports_top_level_state(make_settings_window_with_app):
    window = make_settings_window_with_app()

    class FakeController:
        def __init__(self):
            self._last_snapshot = MCPStatusSnapshot(state="partial", servers=[])

        @property
        def last_snapshot(self):
            return self._last_snapshot

        def redetect_servers(self, servers):
            self._last_snapshot = MCPStatusSnapshot(state="partial", servers=[])
            return self._last_snapshot

    controller = FakeController()
    window.set_mcp_runtime_controller(controller)

    window._redetect_mcp()

    assert "MCP 重新检测完成" in window.save_status_label.text()
    assert "当前状态：partial" in window.save_status_label.text()


def test_settings_window_add_mcp_server_creates_draft_status(make_settings_window_with_app):
    window = make_settings_window_with_app()
    assert window.mcp_server_list.count() == 0

    window._add_mcp_server()

    assert len(window.config.mcp_servers) == 1
    assert window.config.mcp_servers[0].name == "server-1"
    assert window.mcp_server_list.count() == 1
    assert "尚未检测" in window.mcp_server_list.item(0).text()
    assert "已新增 MCP Server 草稿：server-1" in window.save_status_label.text()


def test_settings_window_updates_selected_mcp_server_from_form(make_settings_window_with_app):
    window = make_settings_window_with_app()
    window._add_mcp_server()
    assert len(window.config.mcp_servers) == 1

    window._mcp_selected_row = 0
    window.mcp_name_edit.setText("filesystem")
    window.mcp_json_edit.setPlainText(json.dumps({
        "command": "python",
        "args": ["-m", "mcp_server", "--debug"],
        "env": {"DEBUG": "1", "ROOT": "/tmp/data"},
        "enabled": True,
    }, ensure_ascii=False, indent=2))
    window._update_selected_mcp_server_from_form()

    server = window.config.mcp_servers[0]
    assert server.name == "filesystem"
    assert server.command == "python"
    assert server.args == ["-m", "mcp_server", "--debug"]
    assert server.env == {"DEBUG": "1", "ROOT": "/tmp/data"}
    assert "filesystem" in window.mcp_server_list.item(0).text()


def test_settings_window_save_server_button_persists_current_selection_and_shows_status(make_settings_window_with_app):
    window = make_settings_window_with_app()
    window._add_mcp_server()
    window._mcp_selected_row = 0
    window.mcp_name_edit.setText("filesystem")
    window.mcp_json_edit.setPlainText(json.dumps({
        "command": "python",
        "args": ["-m", "mcp_server"],
        "enabled": True,
    }, ensure_ascii=False, indent=2))

    window.mcp_save_server_button.click()

    server = window.config.mcp_servers[0]
    assert server.name == "filesystem"
    assert server.command == "python"
    assert server.args == ["-m", "mcp_server"]
    assert "已更新 MCP Server 草稿：filesystem。" in window.save_status_label.text()
    assert "保存配置" in window.save_status_label.text()


def test_settings_window_save_config_persists_mcp_servers(tmp_path: Path, make_settings_window_with_app, monkeypatch):
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
    original_mcp = ConfigManager._MCP_CONFIG_PATH
    ConfigManager.reset()
    try:
        ConfigManager._API_CONFIG_PATH = config_root / "api.yaml"
        ConfigManager._API_LOCAL_CONFIG_PATH = config_root / "api.local.yaml"
        ConfigManager._CHARACTERS_CONFIG_PATH = config_root / "characters.yaml"
        ConfigManager._SYSTEM_CONFIG_PATH = config_root / "system_config.yaml"
        ConfigManager._BACKGROUND_CONFIG_PATH = config_root / "background.yaml"
        ConfigManager._MCP_CONFIG_PATH = config_root / "mcp.yaml"

        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
        monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

        window = make_settings_window_with_app()
        window._add_mcp_server()
        assert len(window.config.mcp_servers) == 1
        window._mcp_selected_row = 0
        window.mcp_name_edit.setText("remote-api")
        window.mcp_transport_combo.setCurrentText("http")
        window.mcp_enabled_check.setChecked(True)
        window.mcp_http_url_edit.setText("http://127.0.0.1:8080/mcp")
        window.mcp_json_edit.setPlainText(json.dumps({
            "headers": {"Authorization": "Bearer test-token"},
            "enabled": True,
        }, ensure_ascii=False, indent=2))
        window._update_selected_mcp_server_from_form()
        window.config.save_mcp_servers()

        saved = (config_root / "mcp.yaml").read_text(encoding="utf-8")
        assert "name: remote-api" in saved
        assert "transport: http" in saved
        assert "url: http://127.0.0.1:8080/mcp" in saved
        assert "Authorization: Bearer test-token" in saved
    finally:
        ConfigManager._API_CONFIG_PATH = original_api
        ConfigManager._API_LOCAL_CONFIG_PATH = original_api_local
        ConfigManager._CHARACTERS_CONFIG_PATH = original_characters
        ConfigManager._SYSTEM_CONFIG_PATH = original_system
        ConfigManager._BACKGROUND_CONFIG_PATH = original_background
        ConfigManager._MCP_CONFIG_PATH = original_mcp
        ConfigManager.reset()


def test_settings_window_remove_selected_mcp_server(make_settings_window_with_app):
    window = make_settings_window_with_app()
    window._add_mcp_server()
    window._add_mcp_server()
    assert len(window.config.mcp_servers) == 2

    window._mcp_selected_row = 0
    window._remove_selected_mcp_server()

    assert len(window.config.mcp_servers) == 1
    assert window.config.mcp_servers[0].name == "server-2"
    assert window.mcp_server_list.count() == 1
    assert "已删除 MCP Server：server-1" in window.save_status_label.text()


def test_settings_window_test_selected_mcp_server_requires_controller(make_settings_window_with_app):
    window = make_settings_window_with_app()
    window._add_mcp_server()
    window._mcp_selected_row = 0

    window._test_selected_mcp_server()

    assert "MCP 控制器尚未初始化" in window.save_status_label.text()


def test_settings_window_test_selected_mcp_server_updates_status(make_settings_window_with_app):
    window = make_settings_window_with_app()
    window._add_mcp_server()
    window._mcp_selected_row = 0

    class FakeController:
        def __init__(self):
            self._last_snapshot = MCPStatusSnapshot(state="disabled", servers=[])
            self.tested = []

        @property
        def last_snapshot(self):
            return self._last_snapshot

        def test_server(self, config):
            self.tested.append(config.name)
            return MCPServerStatus(
                name=config.name,
                transport=config.transport,
                enabled=config.enabled,
                state="ready",
                tool_count=3,
                discovered_tools=["read_file", "write_file", "stat_file"],
            )

    controller = FakeController()
    window.set_mcp_runtime_controller(controller)
    window._test_selected_mcp_server()

    assert controller.tested == ["server-1"]
    assert "MCP Server 测试成功：server-1，发现 3 个工具。" in window.save_status_label.text()
    assert "tools=3" in window.mcp_server_list.item(0).text()


def test_saving_mcp_server_does_not_mutate_runtime_snapshot_without_explicit_test_or_redetect(make_settings_window_with_app):
    window = make_settings_window_with_app()
    window._add_mcp_server()
    window._mcp_selected_row = 0
    controller = MCPRuntimeController()
    controller._last_snapshot = MCPStatusSnapshot(
        state="ready",
        servers=[
            MCPServerStatus(
                name="server-1",
                transport="stdio",
                enabled=True,
                state="ready",
                tool_count=1,
                discovered_tools=["old_tool"],
            )
        ],
    )
    window.set_mcp_runtime_controller(controller)
    window.refresh_mcp_status(controller.last_snapshot)
    window.mcp_name_edit.setText("filesystem")
    window.mcp_json_edit.setPlainText(json.dumps({
        "command": "python",
        "args": ["-m", "mcp_server"],
        "enabled": True,
    }, ensure_ascii=False, indent=2))

    window.mcp_save_server_button.click()

    assert controller.last_snapshot.servers[0].name == "server-1"
    assert controller.last_snapshot.servers[0].discovered_tools == ["old_tool"]
    assert "已更新 MCP Server 草稿：filesystem。" in window.save_status_label.text()
