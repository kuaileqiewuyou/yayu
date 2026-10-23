from __future__ import annotations

import json
from dataclasses import dataclass

from core.mcp.config import MCPServerConfig
from core.mcp.status import MCPServerStatus, MCPStatusSnapshot, summarize_mcp_status


@dataclass(frozen=True)
class MCPWorkflowResult:
    snapshot: MCPStatusSnapshot
    message: str
    is_error: bool = False


class MCPSettingsController:
    @staticmethod
    def redetect(runtime, servers) -> MCPWorkflowResult:
        snapshot = runtime.redetect_servers(list(servers))
        if snapshot.state == "invalid_config":
            return MCPWorkflowResult(
                snapshot=snapshot,
                message=f"MCP 配置错误：{snapshot.error}",
                is_error=True,
            )
        return MCPWorkflowResult(
            snapshot=snapshot,
            message=f"MCP 重新检测完成。当前状态：{snapshot.state}。",
        )

    @classmethod
    def test_selected(cls, runtime, servers, row: int) -> MCPWorkflowResult:
        status = runtime.test_server(servers[row])
        snapshot, message, is_error = cls.server_test_result_state(
            snapshot=MCPStatusSnapshot(state="untested", servers=[]),
            row=row,
            status=status,
        )
        if snapshot is None:
            snapshot_servers = [
                MCPServerStatus(
                    name=server.name,
                    transport=server.transport,
                    enabled=server.enabled,
                    state="untested" if server.enabled else "disabled",
                )
                for server in servers
            ]
            snapshot_servers[row] = status
            snapshot = summarize_mcp_status(snapshot_servers)
        return MCPWorkflowResult(snapshot=snapshot, message=message, is_error=is_error)

    @staticmethod
    def server_to_editor_payload(server) -> dict:
        payload = {
            "enabled": server.enabled,
            "timeout": server.timeout,
            "connect_timeout": server.connect_timeout,
        }
        if server.transport == "http":
            payload["url"] = server.url
            payload["headers"] = server.headers
        else:
            payload["command"] = server.command
            payload["args"] = server.args
            payload["env"] = server.env
        return payload

    @staticmethod
    def default_editor_payload() -> dict:
        return {
            "command": "",
            "args": [],
            "env": {},
        }

    @staticmethod
    def server_from_editor_payload(
        *,
        row: int,
        current_server: MCPServerConfig,
        raw_name: str,
        raw_json: str,
        selected_transport: str,
        selected_enabled: bool,
        selected_http_url: str,
    ) -> tuple[MCPServerConfig | None, str | None]:
        name = raw_name.strip() or f"server-{row + 1}"
        json_text = raw_json.strip() or "{}"
        try:
            payload = json.loads(json_text)
        except json.JSONDecodeError as exc:
            return None, f"MCP Server JSON 解析失败：{exc}"
        if not isinstance(payload, dict):
            return None, "MCP Server JSON 必须是对象。"

        transport = selected_transport.strip() if selected_transport.strip() in {"stdio", "http"} else (
            "http" if payload.get("url") else "stdio"
        )
        command = str(payload.get("command", "")).strip()
        args = payload.get("args", [])
        env = payload.get("env", {})
        url = selected_http_url.strip() or str(payload.get("url", "")).strip()
        headers = payload.get("headers", {})
        try:
            timeout = int(payload.get("timeout", current_server.timeout))
        except (TypeError, ValueError):
            return None, "MCP Server JSON 字段 timeout 必须是正整数。"
        if timeout <= 0:
            return None, "MCP Server JSON 字段 timeout 必须是正整数。"
        try:
            connect_timeout = int(payload.get("connect_timeout", current_server.connect_timeout))
        except (TypeError, ValueError):
            return None, "MCP Server JSON 字段 connect_timeout 必须是正整数。"
        if connect_timeout <= 0:
            return None, "MCP Server JSON 字段 connect_timeout 必须是正整数。"

        if transport == "stdio":
            if not isinstance(args, list):
                return None, "MCP Server JSON 字段 args 必须是数组。"
            if not isinstance(env, dict):
                return None, "MCP Server JSON 字段 env 必须是对象。"
            if selected_enabled and not command:
                return None, "MCP Server JSON 字段 command 不能为空。"
            args = [str(value) for value in args]
            env = {str(key): str(value) for key, value in env.items()}
            headers = {}
            url = ""
        else:
            if not isinstance(headers, dict):
                return None, "MCP Server JSON 字段 headers 必须是对象。"
            if selected_enabled and not url:
                return None, "MCP Server HTTP URL 不能为空。"
            headers = {str(key): str(value) for key, value in headers.items()}
            command = ""
            args = []
            env = {}

        return MCPServerConfig(
            name=name,
            transport=transport,
            command=command,
            args=args,
            env=env,
            url=url,
            headers=headers,
            timeout=timeout,
            connect_timeout=connect_timeout,
            enabled=selected_enabled,
        ), None

    @staticmethod
    def add_server_draft(servers) -> tuple[list[MCPServerConfig], int, str]:
        updated_servers = list(servers)
        new_name = f"server-{len(updated_servers) + 1}"
        updated_servers.append(MCPServerConfig(name=new_name, transport="stdio", command="python", args=[]))
        selected_row = len(updated_servers) - 1
        status_message = f"已新增 MCP Server 草稿：{new_name}。请补全配置后点击“保存配置”或“重新检测 MCP”。"
        return updated_servers, selected_row, status_message

    @staticmethod
    def remove_selected_server(
        servers,
        *,
        selected_row: int,
        current_row: int,
    ) -> tuple[list[MCPServerConfig], int, str | None, str | None]:
        row = selected_row if selected_row >= 0 else current_row
        updated_servers = list(servers)
        if row < 0 or row >= len(updated_servers):
            return updated_servers, selected_row, None, "请先选择要删除的 MCP Server。"

        removed_name = updated_servers[row].name
        del updated_servers[row]
        next_selected_row = min(row, len(updated_servers) - 1)
        return updated_servers, next_selected_row, f"已删除 MCP Server：{removed_name}。", None

    @staticmethod
    def server_test_result_state(
        *,
        snapshot: MCPStatusSnapshot,
        row: int,
        status,
    ) -> tuple[MCPStatusSnapshot | None, str, bool]:
        if status.state == "ready":
            message = f"MCP Server 测试成功：{status.name}，发现 {status.tool_count} 个工具。"
            is_error = False
        else:
            message = f"MCP Server 测试失败：{status.name}，错误：{status.error}"
            is_error = True

        snapshot_servers = list(snapshot.servers)
        if row < 0 or row >= len(snapshot_servers):
            return None, message, is_error

        snapshot_servers[row] = status
        summary = summarize_mcp_status(snapshot_servers)
        return summary, message, is_error
