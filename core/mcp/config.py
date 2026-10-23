from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml



@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    transport: str
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    timeout: int = 120
    connect_timeout: int = 60
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_mcp_server_configs(config_path: Path) -> list[MCPServerConfig]:
    if not config_path.exists():
        return []

    with open(config_path, "r", encoding="utf-8") as handle:
        payload: Any = yaml.safe_load(handle) or {}

    server_entries = payload.get("mcp_servers", [])
    if not isinstance(server_entries, list):
        raise ValueError("mcp_servers must be a list")

    configs: list[MCPServerConfig] = []
    for entry in server_entries:
        if not isinstance(entry, dict):
            raise ValueError("mcp_servers entries must be mappings")
        enabled = bool(entry.get("enabled", True))

        name = entry.get("name", "")
        transport = entry.get("transport", "")
        command = entry.get("command", "")
        args = entry.get("args", [])
        env = entry.get("env", {})
        url = entry.get("url", "")
        headers = entry.get("headers", {})
        timeout = entry.get("timeout", 120)
        connect_timeout = entry.get("connect_timeout", 60)

        if not name:
            raise ValueError("mcp server config missing required field: name")
        if not transport:
            raise ValueError("mcp server config missing required field: transport")
        if transport not in {"stdio", "http"}:
            raise ValueError("mcp server config field 'transport' must be 'stdio' or 'http'")
        if enabled and transport == "stdio" and not command:
            raise ValueError("mcp server config missing required field: command")
        if enabled and transport == "http" and not url:
            raise ValueError("mcp server config missing required field: url")
        if command and url:
            raise ValueError("mcp server config must not define both 'command' and 'url'")
        if not isinstance(args, list):
            raise ValueError("mcp server config field 'args' must be a list")
        if not isinstance(env, dict):
            raise ValueError("mcp server config field 'env' must be a mapping")
        if not isinstance(headers, dict):
            raise ValueError("mcp server config field 'headers' must be a mapping")

        configs.append(
            MCPServerConfig(
                name=str(name),
                transport=str(transport),
                command=str(command),
                args=[str(value) for value in args],
                env={str(key): str(value) for key, value in env.items()},
                url=str(url),
                headers={str(key): str(value) for key, value in headers.items()},
                timeout=int(timeout),
                connect_timeout=int(connect_timeout),
                enabled=enabled,
            )
        )

    return configs


def dump_mcp_server_configs(configs: list[MCPServerConfig], config_path: Path) -> None:
    # 延迟导入：避免 config 包（__init__ → config_manager → schema → core.mcp.config）初始化成环。
    from config.atomic_io import atomic_write_text

    payload = {"mcp_servers": [config.to_dict() for config in configs]}
    atomic_write_text(
        config_path,
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
    )
