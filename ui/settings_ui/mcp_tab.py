from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QListWidget,
    QLineEdit,
    QTextEdit,
    QSplitter,
    QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from PySide6.QtCore import Qt

from core.mcp.config import MCPServerConfig
from core.mcp.status import MCPServerStatus, MCPStatusSnapshot
from ui.settings_ui.controls import SafeComboBox
from ui.settings_ui.presentation import page_layout, FlowLayout, ResponsiveColumns, ResponsiveFields, card, release_layout, row_widget
from ui.settings_ui.list_cards import CardListDelegate


@dataclass
class MCPSettingsTabParts:
    widget: QWidget
    redetect_button: QPushButton
    add_server_button: QPushButton
    remove_server_button: QPushButton
    test_server_button: QPushButton
    summary_label: QLabel
    server_list: QListWidget
    empty_state_label: QLabel
    detail_label: QLabel
    name_edit: QLineEdit
    transport_combo: SafeComboBox
    enabled_check: QCheckBox
    http_url_edit: QLineEdit
    json_edit: QTextEdit
    save_server_button: QPushButton
    result_label: QLabel
    tools_table: QTableWidget


def build_mcp_tab(owner) -> MCPSettingsTabParts:
    widget = QWidget()
    widget.setObjectName("mcp_tab")
    widget.setAccessibleName("MCP tab")
    layout = page_layout(widget, "工具 / MCP", "连接外部工具服务。先更新服务器草稿，再使用底部「保存配置」写入配置。")

    actions_layout = FlowLayout()
    redetect_button = QPushButton("重新检测 MCP")
    redetect_button.setObjectName("mcp_redetect_button")
    redetect_button.setAccessibleName("Redetect MCP")
    redetect_button.clicked.connect(owner._redetect_mcp)
    add_server_button = QPushButton("新增 MCP Server")
    add_server_button.setObjectName("mcp_add_server_button")
    add_server_button.setAccessibleName("Add MCP server")
    add_server_button.clicked.connect(owner._add_mcp_server)
    remove_server_button = QPushButton("删除选中 MCP Server")
    remove_server_button.setObjectName("mcp_remove_server_button")
    remove_server_button.setAccessibleName("Remove selected MCP server")
    remove_server_button.clicked.connect(owner._remove_selected_mcp_server)
    test_server_button = QPushButton("测试选中 MCP Server")
    test_server_button.setObjectName("mcp_test_server_button")
    test_server_button.setAccessibleName("Test selected MCP server")
    test_server_button.clicked.connect(owner._test_selected_mcp_server)
    actions_layout.addWidget(redetect_button)
    actions_layout.addWidget(add_server_button)
    actions_layout.addWidget(remove_server_button)
    actions_layout.addWidget(test_server_button)
    actions_layout.addStretch()
    layout.addLayout(actions_layout)

    summary_label = QLabel("MCP 状态：未检测")
    summary_label.setObjectName("mcp_summary_label")
    summary_label.setAccessibleName("MCP summary")
    summary_label.setWordWrap(True)
    layout.addWidget(summary_label)


    left_panel = QWidget()
    left_layout = QVBoxLayout(left_panel)
    left_layout.setContentsMargins(0, 0, 0, 0)
    server_list = QListWidget()
    server_list.setObjectName("mcp_server_list")
    server_list.setAccessibleName("MCP server list")
    server_list.currentRowChanged.connect(owner._show_selected_mcp_server_detail)
    left_layout.addWidget(server_list)
    empty_state_label = QLabel("当前没有可展示的 MCP Server。")
    empty_state_label.setObjectName("mcp_empty_state_label")
    empty_state_label.setAccessibleName("MCP empty state")
    empty_state_label.setWordWrap(True)
    left_layout.addWidget(empty_state_label)
    server_list.setMinimumHeight(180)

    right_panel = QWidget()
    right_layout = QVBoxLayout(right_panel)
    right_layout.setContentsMargins(0, 0, 0, 0)
    detail_label = QLabel("未选择 MCP Server。")
    detail_label.setObjectName("mcp_detail_label")
    detail_label.setAccessibleName("MCP server detail")
    detail_label.setWordWrap(True)
    right_layout.addWidget(detail_label)

    name_title = QLabel("名称")
    right_layout.addWidget(name_title)
    name_edit = QLineEdit()
    name_edit.setObjectName("mcp_name_input")
    name_edit.setAccessibleName("MCP server name")
    name_edit.setPlaceholderText("例如：filesystem")
    right_layout.addWidget(name_edit)

    transport_title = QLabel("Transport")
    right_layout.addWidget(transport_title)
    transport_combo = SafeComboBox()
    transport_combo.setObjectName("mcp_transport_combo")
    transport_combo.setAccessibleName("MCP transport")
    transport_combo.addItems(["stdio", "http"])
    right_layout.addWidget(transport_combo)

    enabled_check = QCheckBox("启用该 MCP Server")
    enabled_check.setObjectName("mcp_enabled_checkbox")
    enabled_check.setAccessibleName("MCP server enabled")
    enabled_check.setChecked(True)
    right_layout.addWidget(enabled_check)

    http_url_title = QLabel("HTTP URL")
    right_layout.addWidget(http_url_title)
    http_url_edit = QLineEdit()
    http_url_edit.setObjectName("mcp_http_url_input")
    http_url_edit.setAccessibleName("MCP HTTP URL")
    http_url_edit.setPlaceholderText("例如：http://127.0.0.1:8080/mcp")
    right_layout.addWidget(http_url_edit)

    json_title = QLabel("服务器 JSON")
    right_layout.addWidget(json_title)
    json_edit = QTextEdit()
    json_edit.setObjectName("mcp_json_input")
    json_edit.setAccessibleName("MCP server JSON")
    json_edit.setPlaceholderText('{\n  "command": "",\n  "args": [],\n  "env": {}\n}')
    right_layout.addWidget(json_edit, 1)

    save_row = QHBoxLayout()
    save_row.addStretch()
    save_server_button = QPushButton("更新服务器草稿")
    save_server_button.setProperty("role", "primary")
    save_server_button.setObjectName("mcp_save_server_button")
    save_server_button.setAccessibleName("Save MCP server")
    save_server_button.clicked.connect(owner._update_selected_mcp_server_from_form)
    save_row.addWidget(save_server_button)
    right_layout.addLayout(save_row)

    release_layout(right_layout)
    config_group, config_layout = card("服务器配置")
    config_layout.addWidget(ResponsiveFields([("名称", name_edit), ("连接方式", transport_combo)], inline=True, breakpoint=560))
    config_layout.addWidget(row_widget([QLabel("HTTP URL"), http_url_edit, enabled_check]))
    config_layout.addWidget(QLabel("服务器 JSON"))
    json_edit.setFixedHeight(140)
    json_edit.setStyleSheet('QTextEdit { font-family: "Cascadia Code", "Consolas"; font-size: 14px; background: #F5F7F2; }')
    config_layout.addWidget(json_edit)
    config_layout.addWidget(save_server_button, alignment=Qt.AlignmentFlag.AlignRight)
    result_group, result_layout = card("连接与工具")
    result_label = QLabel("选择服务器后可测试连接与查看工具。")
    result_label.setWordWrap(True)
    result_layout.addWidget(row_widget([result_label, test_server_button]))
    tools_table = QTableWidget(0, 2)
    tools_table.setObjectName("mcp_tools_table")
    tools_table.setHorizontalHeaderLabels(["工具名称", "说明"])
    tools_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    tools_table.verticalHeader().hide()
    tools_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    tools_table.setFixedHeight(115)
    result_layout.addWidget(tools_table)
    actions_layout.removeWidget(test_server_button)
    right_layout.addWidget(config_group)
    right_layout.addWidget(result_group)
    server_list.setProperty("role", "cards")
    server_list.setItemDelegate(CardListDelegate(server_list, formatter=lambda index: (
        str(index.data()).partition(" - ")[0], str(index.data()).partition(" - ")[2])))
    server_list.setWordWrap(True)
    for control in (name_edit, transport_combo, enabled_check, http_url_edit, json_edit, save_server_button):
        control.show()
    transport_combo.currentTextChanged.connect(lambda value: http_url_edit.setEnabled(value == "http"))
    http_url_edit.setEnabled(transport_combo.currentText() == "http")
    layout.removeWidget(summary_label)
    left_layout.insertWidget(0, summary_label)
    layout.removeItem(actions_layout)
    actions_layout.setParent(None)
    left_layout.addLayout(actions_layout)
    layout.addWidget(ResponsiveColumns([left_panel, right_panel], breakpoint=850, stretches=[1, 2]), 1)

    return MCPSettingsTabParts(
        widget=widget,
        redetect_button=redetect_button,
        add_server_button=add_server_button,
        remove_server_button=remove_server_button,
        test_server_button=test_server_button,
        summary_label=summary_label,
        server_list=server_list,
        empty_state_label=empty_state_label,
        detail_label=detail_label,
        name_edit=name_edit,
        transport_combo=transport_combo,
        enabled_check=enabled_check,
        http_url_edit=http_url_edit,
        json_edit=json_edit,
        save_server_button=save_server_button,
        result_label=result_label,
        tools_table=tools_table,
    )


def format_mcp_summary(snapshot: MCPStatusSnapshot) -> str:
    base = f"MCP 状态：{snapshot.state}"
    if snapshot.error:
        return f"{base}\n错误：{snapshot.error}"
    if not snapshot.servers:
        return base
    enabled_servers = [item for item in snapshot.servers if item.enabled]
    if not enabled_servers:
        return f"{base}\nServer：{len(snapshot.servers)} 个；全部为 disabled"
    ready_count = sum(1 for item in enabled_servers if item.state == "ready")
    failed_count = sum(1 for item in enabled_servers if item.state != "ready")
    return f"{base}\nServer：{len(snapshot.servers)} 个；成功 {ready_count} 个，失败 {failed_count} 个"


def format_mcp_server_row(server: MCPServerStatus) -> str:
    if server.state == "ready":
        suffix = f"tools={server.tool_count}"
    elif server.tool_count:
        suffix = f"tools={server.tool_count}; {server.error or server.state}"
    else:
        suffix = server.error or server.state
    return f"{server.name} [{server.transport}] - {server.state} - {suffix}"


def format_mcp_server_detail(server: MCPServerStatus) -> str:
    details = [
        f"名称：{server.name}",
        f"Transport：{server.transport}",
        f"启用：{'是' if server.enabled else '否'}",
        f"状态：{server.state}",
        f"发现工具数：{server.tool_count}",
    ]
    if hasattr(server, "url") and getattr(server, "url"):
        details.append(f"URL: {server.url}")
    if server.discovered_tools:
        tool_lines = []
        for tool_name in server.discovered_tools:
            description = server.discovered_tool_descriptions.get(tool_name, "")
            if description:
                tool_lines.append(f"- {tool_name}: {description}")
            else:
                tool_lines.append(f"- {tool_name}")
        details.append("发现工具：\n" + "\n".join(tool_lines))
    if server.error:
        details.append(f"错误：{server.error}")
    return "\n".join(details)


def draft_snapshot_for_servers(servers: list[MCPServerConfig]) -> MCPStatusSnapshot:
    if not servers:
        return MCPStatusSnapshot(state="disabled", servers=[])
    return MCPStatusSnapshot(
        state="ready",
        servers=[
            MCPServerStatus(
                name=server.name,
                transport=server.transport,
                enabled=server.enabled,
                state="discover_failed",
                error="尚未检测",
            )
            for server in servers
        ],
    )
