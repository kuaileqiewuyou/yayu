"""T2I 管理器初始化辅助。"""

from __future__ import annotations

from typing import Any

from t2i.t2i_manager import ComfyUIAdapter, T2IAdapterFactory, T2IManager


def create_t2i_manager(config: Any) -> T2IManager | None:
    """根据配置创建 T2IManager；未启用或初始化失败时返回 None。"""
    api_config = getattr(config, "api_config", None)
    if api_config is None:
        return None

    provider = str(getattr(api_config, "t2i_provider", "")).strip().lower()
    if not provider or provider == "none":
        return None

    try:
        adapter_kwargs = {
            "api_url": getattr(api_config, "t2i_api_url", "http://127.0.0.1:8188"),
        }
        if provider == "comfyui":
            checkpoint = str(getattr(api_config, "t2i_checkpoint", "")).strip()
            if checkpoint:
                adapter_kwargs["checkpoint"] = checkpoint
            adapter_kwargs.update(
                poll_attempts=ComfyUIAdapter.DEFAULT_POLL_ATTEMPTS,
                poll_interval=ComfyUIAdapter.DEFAULT_POLL_INTERVAL,
            )

        adapter = T2IAdapterFactory.create_adapter(provider, **adapter_kwargs)
        print(f"[T2I] 已启用: {provider}")
        return T2IManager(adapter)
    except Exception as e:
        print(f"[T2I] 初始化失败: {e}，图像生成功能已禁用")
        return None
