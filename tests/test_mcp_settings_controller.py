import ast
from pathlib import Path

from core.mcp.config import MCPServerConfig
from core.mcp.status import MCPServerStatus, MCPStatusSnapshot
from ui.settings_ui.mcp_controller import MCPSettingsController


def test_mcp_controller_runs_redetect_and_test_workflows_without_private_snapshot_mutation():
    server = MCPServerConfig(name="filesystem", transport="stdio", command="uvx", args=["server"])
    ready = MCPServerStatus(
        name="filesystem",
        transport="stdio",
        enabled=True,
        state="ready",
        tool_count=2,
    )

    class Runtime:
        def __init__(self):
            self.redetected = []
            self.tested = []
            self._last_snapshot = MCPStatusSnapshot(state="untested", servers=[])

        @property
        def last_snapshot(self):
            return self._last_snapshot

        def redetect_servers(self, servers):
            self.redetected.append(servers)
            return MCPStatusSnapshot(state="ready", servers=[ready])

        def test_server(self, selected):
            self.tested.append(selected)
            return ready

    runtime = Runtime()
    controller = MCPSettingsController()

    redetect = controller.redetect(runtime, [server])
    tested = controller.test_selected(runtime, [server], 0)

    assert runtime.redetected == [[server]]
    assert redetect.snapshot.state == "ready"
    assert redetect.message == "MCP 重新检测完成。当前状态：ready。"
    assert redetect.is_error is False
    assert runtime.tested == [server]
    assert tested.snapshot.servers[0] == ready
    assert "测试成功" in tested.message
    assert tested.is_error is False
    assert runtime.last_snapshot.state == "untested"


def test_mcp_controller_builds_stdio_editor_payload_like_settings_window():
    server = MCPServerConfig(
        name="filesystem",
        transport="stdio",
        command="python",
        args=["-m", "server"],
        env={"ROOT": "D:/workspace"},
        timeout=90,
        connect_timeout=15,
        enabled=False,
    )

    assert MCPSettingsController.server_to_editor_payload(server) == {
        "enabled": False,
        "timeout": 90,
        "connect_timeout": 15,
        "command": "python",
        "args": ["-m", "server"],
        "env": {"ROOT": "D:/workspace"},
    }


def test_mcp_controller_builds_http_editor_payload_like_settings_window():
    server = MCPServerConfig(
        name="remote-tools",
        transport="http",
        url="http://127.0.0.1:8080/mcp",
        headers={"Authorization": "Bearer test"},
        timeout=45,
        connect_timeout=10,
        enabled=True,
    )

    assert MCPSettingsController.server_to_editor_payload(server) == {
        "enabled": True,
        "timeout": 45,
        "connect_timeout": 10,
        "url": "http://127.0.0.1:8080/mcp",
        "headers": {"Authorization": "Bearer test"},
    }


def test_mcp_controller_builds_default_editor_payload_like_settings_window():
    assert MCPSettingsController.default_editor_payload() == {
        "command": "",
        "args": [],
        "env": {},
    }


def test_mcp_controller_builds_stdio_server_from_editor_payload_like_settings_window():
    current = MCPServerConfig(name="old", transport="stdio", command="old", timeout=120, connect_timeout=60)

    server, error_message = MCPSettingsController.server_from_editor_payload(
        row=1,
        current_server=current,
        raw_name="  filesystem  ",
        raw_json='{"command":"python","args":["-m",2],"env":{"ROOT":123},"timeout":90,"connect_timeout":15}',
        selected_transport="stdio",
        selected_enabled=False,
        selected_http_url="http://ignored.example/mcp",
    )

    assert error_message is None
    assert server == MCPServerConfig(
        name="filesystem",
        transport="stdio",
        command="python",
        args=["-m", "2"],
        env={"ROOT": "123"},
        timeout=90,
        connect_timeout=15,
        enabled=False,
    )


def test_mcp_controller_builds_http_server_from_editor_payload_like_settings_window():
    current = MCPServerConfig(name="old", transport="http", url="http://old", timeout=120, connect_timeout=60)

    server, error_message = MCPSettingsController.server_from_editor_payload(
        row=2,
        current_server=current,
        raw_name="   ",
        raw_json='{"command":"ignored","args":["ignored"],"env":{"IGNORED":"1"},"url":"http://payload","headers":{"Authorization":123}}',
        selected_transport="http",
        selected_enabled=True,
        selected_http_url="http://selected.example/mcp",
    )

    assert error_message is None
    assert server == MCPServerConfig(
        name="server-3",
        transport="http",
        command="",
        args=[],
        env={},
        url="http://selected.example/mcp",
        headers={"Authorization": "123"},
        timeout=120,
        connect_timeout=60,
        enabled=True,
    )


def test_mcp_controller_reports_editor_payload_validation_errors_like_settings_window():
    current = MCPServerConfig(name="old", transport="stdio", command="python")

    assert MCPSettingsController.server_from_editor_payload(
        row=0,
        current_server=current,
        raw_name="name",
        raw_json="not-json",
        selected_transport="stdio",
        selected_enabled=True,
        selected_http_url="",
    )[1].startswith("MCP Server JSON 解析失败：")
    assert MCPSettingsController.server_from_editor_payload(
        row=0,
        current_server=current,
        raw_name="name",
        raw_json="[]",
        selected_transport="stdio",
        selected_enabled=True,
        selected_http_url="",
    )[1] == "MCP Server JSON 必须是对象。"
    assert MCPSettingsController.server_from_editor_payload(
        row=0,
        current_server=current,
        raw_name="name",
        raw_json='{"args": "not-list"}',
        selected_transport="stdio",
        selected_enabled=True,
        selected_http_url="",
    )[1] == "MCP Server JSON 字段 args 必须是数组。"
    assert MCPSettingsController.server_from_editor_payload(
        row=0,
        current_server=current,
        raw_name="name",
        raw_json='{"env": []}',
        selected_transport="stdio",
        selected_enabled=True,
        selected_http_url="",
    )[1] == "MCP Server JSON 字段 env 必须是对象。"
    assert MCPSettingsController.server_from_editor_payload(
        row=0,
        current_server=current,
        raw_name="name",
        raw_json='{"headers": []}',
        selected_transport="http",
        selected_enabled=True,
        selected_http_url="http://example/mcp",
    )[1] == "MCP Server JSON 字段 headers 必须是对象。"


def test_mcp_controller_rejects_enabled_server_without_transport_target():
    current = MCPServerConfig(name="old", transport="stdio", command="python")

    stdio_server, stdio_error = MCPSettingsController.server_from_editor_payload(
        row=0,
        current_server=current,
        raw_name="stdio-server",
        raw_json="{}",
        selected_transport="stdio",
        selected_enabled=True,
        selected_http_url="",
    )
    http_server, http_error = MCPSettingsController.server_from_editor_payload(
        row=1,
        current_server=current,
        raw_name="http-server",
        raw_json="{}",
        selected_transport="http",
        selected_enabled=True,
        selected_http_url="",
    )

    assert stdio_server is None
    assert stdio_error == "MCP Server JSON 字段 command 不能为空。"
    assert http_server is None
    assert http_error == "MCP Server HTTP URL 不能为空。"


def test_mcp_controller_allows_incomplete_disabled_server_drafts():
    current = MCPServerConfig(name="old", transport="stdio", command="python")

    stdio_server, stdio_error = MCPSettingsController.server_from_editor_payload(
        row=0,
        current_server=current,
        raw_name="disabled-stdio",
        raw_json="{}",
        selected_transport="stdio",
        selected_enabled=False,
        selected_http_url="",
    )
    http_server, http_error = MCPSettingsController.server_from_editor_payload(
        row=1,
        current_server=current,
        raw_name="disabled-http",
        raw_json="{}",
        selected_transport="http",
        selected_enabled=False,
        selected_http_url="",
    )

    assert stdio_error is None
    assert stdio_server.enabled is False
    assert stdio_server.command == ""
    assert http_error is None
    assert http_server.enabled is False
    assert http_server.url == ""


def test_mcp_controller_reports_invalid_timeout_fields_as_editor_errors():
    current = MCPServerConfig(name="old", transport="stdio", command="python")

    _, timeout_error = MCPSettingsController.server_from_editor_payload(
        row=0,
        current_server=current,
        raw_name="name",
        raw_json='{"timeout": "abc"}',
        selected_transport="stdio",
        selected_enabled=True,
        selected_http_url="",
    )
    _, connect_timeout_error = MCPSettingsController.server_from_editor_payload(
        row=0,
        current_server=current,
        raw_name="name",
        raw_json='{"connect_timeout": 0}',
        selected_transport="stdio",
        selected_enabled=True,
        selected_http_url="",
    )

    assert timeout_error == "MCP Server JSON 字段 timeout 必须是正整数。"
    assert connect_timeout_error == "MCP Server JSON 字段 connect_timeout 必须是正整数。"


def test_mcp_controller_adds_server_draft_like_settings_window():
    existing = [MCPServerConfig(name="alpha", transport="stdio", command="python", args=["-m", "alpha"])]

    servers, selected_row, status_message = MCPSettingsController.add_server_draft(existing)

    assert existing == [MCPServerConfig(name="alpha", transport="stdio", command="python", args=["-m", "alpha"])]
    assert servers == [
        MCPServerConfig(name="alpha", transport="stdio", command="python", args=["-m", "alpha"]),
        MCPServerConfig(name="server-2", transport="stdio", command="python", args=[]),
    ]
    assert selected_row == 1
    assert status_message == "已新增 MCP Server 草稿：server-2。请补全配置后点击“保存配置”或“重新检测 MCP”。"


def test_mcp_controller_removes_selected_server_like_settings_window():
    servers = [
        MCPServerConfig(name="alpha", transport="stdio", command="python"),
        MCPServerConfig(name="beta", transport="http", url="http://example/mcp"),
        MCPServerConfig(name="gamma", transport="stdio", command="uvx"),
    ]

    updated, selected_row, status_message, error_message = MCPSettingsController.remove_selected_server(
        servers,
        selected_row=1,
        current_row=0,
    )

    assert servers == [
        MCPServerConfig(name="alpha", transport="stdio", command="python"),
        MCPServerConfig(name="beta", transport="http", url="http://example/mcp"),
        MCPServerConfig(name="gamma", transport="stdio", command="uvx"),
    ]
    assert updated == [
        MCPServerConfig(name="alpha", transport="stdio", command="python"),
        MCPServerConfig(name="gamma", transport="stdio", command="uvx"),
    ]
    assert selected_row == 1
    assert status_message == "已删除 MCP Server：beta。"
    assert error_message is None


def test_mcp_controller_removes_current_row_when_no_selected_row_like_settings_window():
    servers = [
        MCPServerConfig(name="alpha", transport="stdio", command="python"),
        MCPServerConfig(name="beta", transport="stdio", command="uvx"),
    ]

    updated, selected_row, status_message, error_message = MCPSettingsController.remove_selected_server(
        servers,
        selected_row=-1,
        current_row=0,
    )

    assert updated == [MCPServerConfig(name="beta", transport="stdio", command="uvx")]
    assert selected_row == 0
    assert status_message == "已删除 MCP Server：alpha。"
    assert error_message is None


def test_mcp_controller_reports_remove_without_selection_like_settings_window():
    servers = [MCPServerConfig(name="alpha", transport="stdio", command="python")]

    updated, selected_row, status_message, error_message = MCPSettingsController.remove_selected_server(
        servers,
        selected_row=-1,
        current_row=-1,
    )

    assert updated == servers
    assert selected_row == -1
    assert status_message is None
    assert error_message == "请先选择要删除的 MCP Server。"


def test_mcp_controller_builds_ready_test_result_snapshot_like_settings_window():
    snapshot = MCPStatusSnapshot(
        state="partial",
        servers=[
            MCPServerStatus(name="alpha", transport="stdio", enabled=True, state="ready", tool_count=2),
            MCPServerStatus(name="beta", transport="stdio", enabled=True, state="discover_failed", error="old"),
        ],
    )
    status = MCPServerStatus(
        name="beta",
        transport="stdio",
        enabled=True,
        state="ready",
        tool_count=3,
        discovered_tools=["search", "read", "write"],
    )

    updated_snapshot, message, is_error = MCPSettingsController.server_test_result_state(
        snapshot=snapshot,
        row=1,
        status=status,
    )

    assert updated_snapshot == MCPStatusSnapshot(
        state="ready",
        servers=[
            MCPServerStatus(name="alpha", transport="stdio", enabled=True, state="ready", tool_count=2),
            status,
        ],
    )
    assert message == "MCP Server 测试成功：beta，发现 3 个工具。"
    assert is_error is False


def test_mcp_controller_builds_partial_test_result_snapshot_like_settings_window():
    snapshot = MCPStatusSnapshot(
        state="ready",
        servers=[
            MCPServerStatus(name="alpha", transport="stdio", enabled=True, state="ready", tool_count=2),
            MCPServerStatus(name="beta", transport="stdio", enabled=True, state="ready", tool_count=1),
        ],
    )
    status = MCPServerStatus(
        name="beta",
        transport="stdio",
        enabled=True,
        state="discover_failed",
        error="boom",
    )

    updated_snapshot, message, is_error = MCPSettingsController.server_test_result_state(
        snapshot=snapshot,
        row=1,
        status=status,
    )

    assert updated_snapshot == MCPStatusSnapshot(
        state="partial",
        servers=[
            MCPServerStatus(name="alpha", transport="stdio", enabled=True, state="ready", tool_count=2),
            status,
        ],
    )
    assert message == "MCP Server 测试失败：beta，错误：boom"
    assert is_error is True


def test_mcp_controller_builds_failed_test_result_snapshot_like_settings_window():
    snapshot = MCPStatusSnapshot(
        state="failed",
        servers=[
            MCPServerStatus(name="alpha", transport="stdio", enabled=True, state="discover_failed", error="old"),
            MCPServerStatus(name="beta", transport="stdio", enabled=True, state="ready", tool_count=1),
        ],
    )
    status = MCPServerStatus(
        name="beta",
        transport="stdio",
        enabled=True,
        state="start_failed",
        error="cannot start",
    )

    updated_snapshot, message, is_error = MCPSettingsController.server_test_result_state(
        snapshot=snapshot,
        row=1,
        status=status,
    )

    assert updated_snapshot == MCPStatusSnapshot(
        state="failed",
        servers=[
            MCPServerStatus(name="alpha", transport="stdio", enabled=True, state="discover_failed", error="old"),
            status,
        ],
    )
    assert message == "MCP Server 测试失败：beta，错误：cannot start"
    assert is_error is True


def test_mcp_controller_ignores_disabled_servers_when_summarizing_test_result():
    snapshot = MCPStatusSnapshot(
        state="disabled",
        servers=[
            MCPServerStatus(name="disabled", transport="stdio", enabled=False, state="disabled"),
            MCPServerStatus(name="active", transport="stdio", enabled=True, state="discover_failed", error="old"),
        ],
    )
    status = MCPServerStatus(
        name="active",
        transport="stdio",
        enabled=True,
        state="ready",
        tool_count=2,
    )

    updated_snapshot, _, is_error = MCPSettingsController.server_test_result_state(
        snapshot=snapshot,
        row=1,
        status=status,
    )

    assert updated_snapshot.state == "ready"
    assert is_error is False


def test_mcp_controller_keeps_snapshot_unmodified_when_test_row_is_out_of_range_like_settings_window():
    snapshot = MCPStatusSnapshot(
        state="ready",
        servers=[MCPServerStatus(name="alpha", transport="stdio", enabled=True, state="ready", tool_count=2)],
    )
    status = MCPServerStatus(name="ghost", transport="stdio", enabled=True, state="ready", tool_count=1)

    updated_snapshot, message, is_error = MCPSettingsController.server_test_result_state(
        snapshot=snapshot,
        row=5,
        status=status,
    )

    assert updated_snapshot is None
    assert message == "MCP Server 测试成功：ghost，发现 1 个工具。"
    assert is_error is False


def test_settings_window_mcp_payload_aliases_delegate_to_controller():
    window_path = Path(__file__).resolve().parents[1] / "ui" / "settings_ui" / "window.py"
    source = window_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    settings_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SettingsWindow")
    methods = {
        node.name: ast.get_source_segment(source, node)
        for node in settings_class.body
        if isinstance(node, ast.FunctionDef)
    }

    assert "MCPSettingsController.server_to_editor_payload(server)" in methods["_mcp_server_to_editor_payload"]
    assert '"command": server.command' not in methods["_mcp_server_to_editor_payload"]
    assert "MCPSettingsController.default_editor_payload()" in methods["_default_mcp_editor_payload"]
    assert '"command": ""' not in methods["_default_mcp_editor_payload"]
    update_source = methods["_update_selected_mcp_server_from_form"]
    assert "MCPSettingsController.server_from_editor_payload" in update_source
    assert "json.loads(raw_json)" not in update_source
    assert "MCPServerConfig(" not in update_source
    add_source = methods["_add_mcp_server"]
    assert "MCPSettingsController.add_server_draft" in add_source
    assert "MCPServerConfig(" not in add_source
    assert "server-{len(servers) + 1}" not in add_source
    remove_source = methods["_remove_selected_mcp_server"]
    assert "MCPSettingsController.remove_selected_server" in remove_source
    assert "del servers[row]" not in remove_source
    test_source = methods["_test_selected_mcp_server"]
    assert "if not self._update_selected_mcp_server_from_form():" in test_source
    assert "MCPSettingsController.test_selected" in test_source
    assert "MCPSettingsController.server_test_result_state" not in test_source
    assert "overall_state =" not in test_source
    assert "ready_count =" not in test_source
    assert "MCPStatusSnapshot(" not in test_source
    assert "_redetect_mcp" in methods
    assert "redetect()" not in update_source
