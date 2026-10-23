"""Render the real chat widget offscreen using public demo data, without services.

Python 3.10 compatibility is limited to this process; project sources are untouched.
Use --frames 0 100 200 to sample the existing overlay fade-out animation.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime
import json
import os
from pathlib import Path
import platform
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def isolated_runtime():
    """Keep every config and relative runtime path away from the real profile.

    Call before importing UI modules. State is restored even when rendering
    fails, so importing this helper from another offline tool is safe.
    """
    from config.config_manager import ConfigManager

    config_files = {
        "_API_CONFIG_PATH": "api.yaml",
        "_API_LOCAL_CONFIG_PATH": "api.local.yaml",
        "_CHARACTERS_CONFIG_PATH": "characters.yaml",
        "_SYSTEM_CONFIG_PATH": "system_config.yaml",
        "_BACKGROUND_CONFIG_PATH": "background.yaml",
        "_MCP_CONFIG_PATH": "mcp.yaml",
    }
    original_paths = {name: getattr(ConfigManager, name) for name in config_files}
    original_instance, original_config = ConfigManager._instance, ConfigManager._config
    original_cwd = Path.cwd()
    original_local_data = os.environ.get("LOCALAPPDATA")
    with tempfile.TemporaryDirectory(prefix="galgame-ui-snapshot-") as runtime_dir:
        try:
            config_root = Path(runtime_dir) / "data" / "config"
            for name, filename in config_files.items():
                setattr(ConfigManager, name, config_root / filename)
            ConfigManager.reset()
            os.environ["LOCALAPPDATA"] = runtime_dir
            os.chdir(runtime_dir)
            yield Path(runtime_dir)
        finally:
            ConfigManager.reset()
            for name, value in original_paths.items():
                setattr(ConfigManager, name, value)
            ConfigManager._instance, ConfigManager._config = original_instance, original_config
            os.chdir(original_cwd)
            if original_local_data is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = original_local_data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / ".sandbox" / "snapshots")
    parser.add_argument("--width", type=int, default=820)
    parser.add_argument("--height", type=int, default=760)
    parser.add_argument("--sprite", type=Path, help="Optional local demo sprite; otherwise use a labelled placeholder.")
    parser.add_argument("--font", type=Path, help="Optional local CJK font (.ttf/.ttc/.otf).")
    parser.add_argument("--frames", type=int, nargs="+", help="Fade-out sample times in milliseconds, e.g. 0 100 200.")
    args = parser.parse_args()
    if args.width < 640 or args.height < 520:
        parser.error("ChatUIWindow requires at least 640 x 520 pixels.")
    if args.frames is not None and min(args.frames) < 0:
        parser.error("Frame times must be non-negative.")
    for path in (args.sprite, args.font):
        if path is not None and not path.is_file():
            parser.error(f"File does not exist: {path}")
    args.sprite = args.sprite.resolve() if args.sprite else None
    args.font = args.font.resolve() if args.font else None

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_SCALE_FACTOR"] = "1"
    os.environ["QT_FONT_DPI"] = "96"
    utc_compat = not hasattr(datetime, "UTC")
    if utc_compat:
        datetime.UTC = datetime.timezone.utc
    sys.path.insert(0, str(PROJECT_ROOT))
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Isolate configurations and relative data paths before any UI import.
    with isolated_runtime():
        import PySide6
        from PySide6.QtCore import QRectF, Qt, qVersion
        from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QLinearGradient, QPainter, QPixmap
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from ui.chat_ui.chat_ui import ChatUIWindow

        app = QApplication([])
        if args.font:
            font_id = QFontDatabase.addApplicationFont(str(args.font.resolve()))
            if font_id == -1:
                raise RuntimeError(f"Qt could not load font: {args.font}")
            family = QFontDatabase.applicationFontFamilies(font_id)[0]
        else:
            available = set(QFontDatabase.families())
            family = next((name for name in ("Noto Sans CJK SC", "Noto Sans SC", "Microsoft YaHei UI", "Microsoft YaHei") if name in available), app.font().family())
        app.setFont(QFont(family, 10))

        window = ChatUIWindow()
        if args.font:
            app.setFont(QFont(family, 10))
        try:
            window.resize(args.width, args.height)
            sprite_path = args.sprite.resolve() if args.sprite else args.output_dir / "placeholder-sprite.png"
            if not args.sprite:
                placeholder = QImage(360, 580, QImage.Format.Format_ARGB32_Premultiplied)
                placeholder.fill(Qt.GlobalColor.transparent)
                painter = QPainter(placeholder)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#a9b9aa"))
                painter.drawEllipse(QRectF(110, 35, 140, 160))
                painter.setBrush(QColor("#c4cfc0"))
                painter.drawRoundedRect(QRectF(65, 195, 230, 360), 90, 90)
                painter.setPen(QColor("#34463b"))
                painter.drawText(placeholder.rect(), Qt.AlignmentFlag.AlignCenter, "离线测试\n占位立绘")
                painter.end()
                if not placeholder.save(str(sprite_path)):
                    raise RuntimeError("Could not save placeholder sprite.")
            if QPixmap(str(sprite_path)).isNull():
                raise RuntimeError(f"Qt could not decode sprite: {sprite_path}")
            window.set_sprite(str(sprite_path))
            window.add_message("你好，欢迎来到离线渲染测试。这里的台词、资料卡和选项都是演示数据。", char_name="测试角色")
            window.add_card("## 离线渲染验证\n- 中文文本与布局\n- Markdown 资料卡\n- 真实 Qt 控件\n\n```python\nprint('Qt offscreen OK')\n```", title="演示资料卡")
            window.post_options(["查看布局", "继续对话"])
            window.show()
            # 静态截图应是“静止后的终态”：补全逐字显示、跳过进入动效。
            if hasattr(window.current_message_label, "complete_reveal"):
                window.current_message_label.complete_reveal()
            QTest.qWait(450)
            app.processEvents()

            captures = []

            def capture(stem: str, time_ms: int | None = None) -> None:
                transparent = window.grab().toImage()
                transparent_path = args.output_dir / f"{stem}-transparent.png"
                composite_path = args.output_dir / f"{stem}.png"
                if transparent.isNull() or not transparent.save(str(transparent_path)):
                    raise RuntimeError("Qt returned an empty image or could not save it.")
                composite = QImage(transparent.size(), QImage.Format.Format_RGB32)
                painter = QPainter(composite)
                gradient = QLinearGradient(0, 0, 0, composite.height())
                gradient.setColorAt(0, QColor("#e4ecdf"))
                gradient.setColorAt(1, QColor("#c2d0c3"))
                painter.fillRect(composite.rect(), gradient)
                painter.drawImage(0, 0, transparent)
                painter.end()
                if not composite.save(str(composite_path)):
                    raise RuntimeError("Could not save composited image.")
                effect = window.overlay_layer.graphicsEffect()
                captures.append({
                    "file": composite_path.name,
                    "transparent_file": transparent_path.name,
                    "time_ms": time_ms,
                    "size": [transparent.width(), transparent.height()],
                    "overlay_visible": window.overlay_layer.isVisible(),
                    "overlay_opacity": effect.opacity() if effect else 1.0,
                    "content_scroll": window.scroll_area.verticalScrollBar().value(),
                })

            capture("chat")
            window.scroll_area.verticalScrollBar().setValue(0)
            app.processEvents()
            capture("chat-card")
            if args.frames:
                window.toggle_ui_visibility()
                animation = window._overlay_anim
                if animation is None:
                    raise RuntimeError("The chat UI did not start its fade-out animation.")
                animation.pause()
                duration = animation.duration()
                completed = False
                for time_ms in sorted(set(args.frames)):
                    if not completed:
                        animation.setCurrentTime(min(time_ms, duration))
                        completed = time_ms >= duration
                    app.processEvents()
                    capture(f"fade-{time_ms:04d}ms", time_ms)

            metadata = {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "pyside6": PySide6.__version__,
                "qt": qVersion(),
                "qpa": app.platformName(),
                "font": app.font().family(),
                "python310_utc_compat": utc_compat,
                "demo_sprite": not bool(args.sprite),
                "background": "Synthetic gradient; transparent originals are saved alongside.",
                "animation": "Existing chat overlay fade-out; fixed animation times, not a smoothness benchmark.",
                "captures": captures,
            }
            manifest_path = args.output_dir / "manifest.json"
            manifest_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"status": "ok", "manifest": str(manifest_path), "captures": len(captures)}, ensure_ascii=False))
        finally:
            window.close()
            app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
