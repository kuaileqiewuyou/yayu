"""Runtime startup notices for configuration preflight checks."""
from __future__ import annotations

from typing import Any


def mcp_status_startup_notice(snapshot: Any) -> str:
    """Return a startup notice summarizing MCP availability for the chat window."""
    if snapshot is None:
        return ""
    state = getattr(snapshot, "state", "")
    servers = list(getattr(snapshot, "servers", []) or [])
    error = str(getattr(snapshot, "error", "") or "").strip()
    if state in {"", "disabled"}:
        return ""
    if state == "invalid_config":
        return f"MCP 配置无效：{error}" if error else "MCP 配置无效。"
    if not servers:
        return ""
    ready_count = sum(1 for item in servers if getattr(item, "state", "") == "ready")
    failed_count = sum(1 for item in servers if getattr(item, "state", "") == "failed")
    if state == "ready":
        return f"MCP 已加载：{ready_count} 个 server 可用，{sum(getattr(item, 'tool_count', 0) for item in servers)} 个工具已注册。"
    if state == "partial":
        return f"MCP 部分可用：成功 {ready_count} 个，失败 {failed_count} 个。可在设置中查看详情。"
    if state == "failed":
        return f"MCP 加载失败：{failed_count} 个 server 启动失败。可在设置中查看详情。"
    return ""


def apply_mcp_status_startup_notice(window: Any, snapshot: Any) -> str:
    """Apply the MCP startup status summary to the chat window when useful."""
    message = mcp_status_startup_notice(snapshot)
    if message:
        window.set_reply_status(message, error=(getattr(snapshot, "state", "") in {"invalid_config", "failed", "partial"}))
    return message


def _trimmed(value: Any) -> str:
    """Return a stripped string value for configuration presence checks."""
    return "" if value is None else str(value).strip()


def llm_config_startup_notice(config: Any) -> str:
    """Return a startup notice when required LLM configuration is incomplete."""
    api_config = getattr(config, "api_config", None)
    if api_config is None:
        return "LLM 配置不完整：API 配置。请先在设置中补全后再开始对话。"

    provider = _trimmed(getattr(api_config, "llm_provider", ""))
    base_url = _trimmed(getattr(api_config, "llm_base_url", ""))

    missing: list[str] = []
    if not provider:
        missing.append("LLM 供应商")

    api_keys = getattr(api_config, "llm_api_key", {}) or {}
    if not isinstance(api_keys, dict):
        api_keys = {}
    api_key = _trimmed(api_keys.get(provider, "")) if provider else ""
    if not api_key:
        missing.append("API Key")

    if not base_url:
        missing.append("Base URL")

    models = getattr(api_config, "llm_model", {}) or {}
    if not isinstance(models, dict):
        models = {}
    model = _trimmed(models.get(provider, "")) if provider else ""
    if not model:
        missing.append("模型 ID")

    if not missing:
        return ""
    return f"LLM 配置不完整：{'、'.join(missing)}。请先在设置中补全后再开始对话。"


def apply_llm_config_startup_notice(window: Any, config: Any) -> str:
    """Apply the LLM startup configuration notice to the window when needed."""
    message = llm_config_startup_notice(config)
    if message:
        window.set_config_notice(message)
    return message
