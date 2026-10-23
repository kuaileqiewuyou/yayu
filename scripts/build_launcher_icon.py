"""Encode the launcher artwork as a multi-resolution Windows ICO.

Run with the project's venv Python; uses the existing PySide6 dependency.
"""

from pathlib import Path
import struct

from PySide6.QtCore import QBuffer, QIODevice, QSize, Qt
from PySide6.QtGui import QImage


def main() -> None:
    assets = Path(__file__).resolve().parents[1] / "ui" / "assets"
    source = QImage(str(assets / "yayu.png"))
    if source.isNull():
        raise SystemExit("Cannot read ui/assets/yayu.png")
    sizes = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
    entries = []
    frames = []
    offset = 6 + 16 * len(sizes)
    for size in sizes:
        frame = source.scaled(
            QSize(size, size), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not frame.save(buffer, "PNG"):
            raise SystemExit(f"Cannot encode {size}px icon")
        payload = bytes(buffer.data())
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(payload), offset))
        frames.append(payload)
        offset += len(payload)
    target = assets / "yayu.ico"
    target.write_bytes(struct.pack("<HHH", 0, 1, len(sizes)) + b"".join(entries) + b"".join(frames))
    print(f"Built {target} ({len(sizes)} sizes)")


if __name__ == "__main__":
    main()
