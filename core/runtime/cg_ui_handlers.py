"""CG/T2I UI result handlers."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def handle_t2i_image_generated(window: Any, result: str) -> None:
    """Update CG status and preview existing local image results."""
    if not result:
        window.set_reply_status("CG 生成未返回图片", error=True)
        return
    if result.startswith("comfyui://prompt/"):
        window.set_reply_status(f"CG 已提交到 ComfyUI，但暂未取得图片：{result}")
        return
    if result.startswith("comfyui://image/"):
        window.set_reply_status(f"CG 已生成，但本地缓存不可用：{result}")
        return
    if result.startswith("comfyui://"):
        window.set_reply_status(f"CG 返回 ComfyUI 结果：{result}")
        return

    window.set_reply_status(f"CG 生成完成：{result}")
    try:
        path = Path(result)
        if path.exists() and hasattr(window, "add_cg_preview"):
            window.add_cg_preview(str(path))
    except OSError:
        return
