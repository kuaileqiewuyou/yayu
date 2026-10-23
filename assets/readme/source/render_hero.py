"""Rebuild the selected README hero with the project's existing Qt dependency."""
import argparse
import base64
import os
from pathlib import Path
import re

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parents[2]
ASSETS = SOURCE.parent

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ASSETS / "hero.png")
    parser.add_argument("--font-family", help="Override the default installed CJK font")
    args = parser.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QByteArray, Qt
    from PySide6.QtGui import QFontDatabase, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    bundled_font = ROOT / "ui/assets/fonts/ChillRoundF.ttf"
    font_id = QFontDatabase.addApplicationFont(str(bundled_font)) if bundled_font.is_file() else -1
    if args.font_family:
        family = args.font_family
    elif font_id >= 0:
        family = QFontDatabase.applicationFontFamilies(font_id)[0]
    else:
        installed = set(QFontDatabase.families())
        preferred = ("Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", "PingFang SC")
        family = next((name for name in preferred if name in installed), None)
        if family is None:
            raise SystemExit("Install a CJK font or pass --font-family <installed-font>.")
    svg = (SOURCE / "hero-layout.svg").read_text(encoding="utf-8")
    # Qt's SVG renderer needs a single registered family. The editable layout
    # retains its system-font fallbacks for opening in a browser or editor.
    svg = re.sub(r'font-family="[^"]+"', f'font-family="{family}"', svg)
    image_data = base64.b64encode((ASSETS / "chat-demo.png").read_bytes()).decode("ascii")
    svg = svg.replace('xlink:href="../chat-demo.png"', f'xlink:href="data:image/png;base64,{image_data}"')
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    if not renderer.isValid():
        raise SystemExit("Invalid hero SVG layout.")
    image = QImage(renderer.defaultSize(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(args.output)):
        raise SystemExit(f"Cannot save {args.output}")
    print(args.output.resolve())

if __name__ == "__main__":
    main()

