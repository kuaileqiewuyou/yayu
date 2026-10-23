from __future__ import annotations

from urllib import request
from urllib.error import HTTPError, URLError


class APISettingsController:
    """Pure API/LLM settings helpers extracted from SettingsWindow."""

    @staticmethod
    def llm_config_status_message(
        *,
        provider: str,
        api_key: str,
        base_url: str,
        model: str,
        saved: bool = False,
    ) -> tuple[str, bool]:
        provider = provider.strip()
        api_key = api_key.strip()
        base_url = base_url.strip()
        model = model.strip()

        missing = []
        if not provider:
            missing.append("LLM 供应商")
        if not api_key:
            missing.append("API Key")
        if not base_url:
            missing.append("Base URL")
        if not model:
            missing.append("模型 ID")

        prefix = "配置已保存。" if saved else ""
        if missing:
            return f"{prefix}LLM 配置不完整：{'、'.join(missing)}。", True

        return f"{prefix}LLM 配置看起来可用：{provider} / {model}。保存后请重启聊天窗口后生效。", False

    @staticmethod
    def comfyui_connection_status(
        *,
        provider: str,
        base_url: str,
        urlopen=None,
        timeout: float = 2.0,
    ) -> tuple[str, bool]:
        """Return the user-facing ComfyUI connection test status."""
        if provider != "comfyui":
            return "请先将 T2I / CG 引擎切换为 comfyui 后再测试连接。", True

        normalized_base_url = base_url.strip().rstrip("/")
        if not normalized_base_url:
            return "ComfyUI API URL 不能为空。", True

        opener = urlopen or request.urlopen
        try:
            req = request.Request(f"{normalized_base_url}/system_stats", method="GET")
            with opener(req, timeout=timeout) as response:
                response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as e:
            return f"ComfyUI 连接失败：{e}", True

        return "ComfyUI 连接成功。", False
