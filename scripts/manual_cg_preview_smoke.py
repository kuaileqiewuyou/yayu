"""手动 CG 预览验收脚本。

不经过 LLM/ComfyUI，直接启动 ChatUIWindow 并注入一张本地 PNG，方便手动验证：
缩略图、大图预览、“打开图片”、“CG目录”按钮和窗口响应性。
"""
from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication

from ui.chat_ui.chat_ui import ChatUIWindow


def _minimal_png_rgba(width: int = 2, height: int = 2) -> bytes:
    """Return a tiny valid RGBA PNG generated locally for manual CG preview smoke."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        payload = kind + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    # 生成简单的 2x2 暖色像素，便于肉眼确认不是空白区域。
    pixels = [
        b"\xff\xb0\x5c\xff",
        b"\xff\xdf\x87\xff",
        b"\x7a\x5c\xff\xff",
        b"\x35\x2f\x4f\xff",
    ]
    rows = []
    for row in range(height):
        row_bytes = b""
        for col in range(width):
            row_bytes += pixels[(row * width + col) % len(pixels)]
        rows.append(b"\x00" + row_bytes)
    raw = b"".join(rows)

    return b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
            chunk(b"IDAT", zlib.compress(raw)),
            chunk(b"IEND", b""),
        ]
    )


def _write_smoke_png() -> Path:
    image_path = PROJECT_ROOT / "data" / "cg" / "generated" / "manual-preview-smoke.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(_minimal_png_rgba())
    return image_path.resolve()


def main() -> int:
    app = QApplication([])
    window = ChatUIWindow()

    image_path = _write_smoke_png()
    window.add_message("[CG] 手动预览验收：夕阳下的教室", is_user=False, char_name="系统")
    window.set_reply_status(f"CG 生成完成：{image_path}")
    window.add_cg_preview(str(image_path))
    window.show()

    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
