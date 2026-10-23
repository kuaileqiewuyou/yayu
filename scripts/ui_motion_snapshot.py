"""Sample chat-window motion at fixed timestamps (offscreen, no services).

Renders the real ChatUIWindow with two sprite images and captures frames of:
  - sprite crossfade (neutral -> happy)
  - speak hop
  - idle breathing (peak / trough)
Time is injected via the widget's progress helpers, so frames are deterministic.
Output: .sandbox/snapshots/motion/*.png + a contact sheet motion-sheet.png
"""
from __future__ import annotations

import argparse
import datetime
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / ".sandbox" / "snapshots" / "motion")
    starter = PROJECT_ROOT / "data" / "characters" / "xiaoya"
    parser.add_argument("--sprite-a", type=Path, default=starter / "standing-neutral.png")
    parser.add_argument("--sprite-b", type=Path, default=starter / "standing-wink.png")
    parser.add_argument("--width", type=int, default=820)
    parser.add_argument("--height", type=int, default=760)
    args = parser.parse_args()
    if args.width < 640 or args.height < 520:
        parser.error("ChatUIWindow requires at least 640 x 520 pixels.")
    for path in (args.sprite_a, args.sprite_b):
        if not path.is_file():
            parser.error(f"File does not exist: {path}")
    args.sprite_a = args.sprite_a.resolve()
    args.sprite_b = args.sprite_b.resolve()

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_SCALE_FACTOR"] = "1"
    if not hasattr(datetime, "UTC"):
        datetime.UTC = datetime.timezone.utc
    sys.path.insert(0, str(PROJECT_ROOT))
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    from scripts.ui_snapshot import isolated_runtime

    with isolated_runtime():
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QLinearGradient, QPainter
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from ui import motion
        from ui.chat_ui.chat_ui import ChatUIWindow

        app = QApplication([])
        fams = set(QFontDatabase.families())
        family = next((f for f in ("Noto Sans CJK SC", "Microsoft YaHei UI") if f in fams), app.font().family())
        app.setFont(QFont(family, 10))

        window = ChatUIWindow()
        window.resize(args.width, args.height)
        window.show()
        QTest.qWait(50)
        sprite = window.sprite_widget
        sprite._frame_timer.stop()

        def grab(name: str, label: str) -> QImage:
            sprite._frame_timer.stop()
            img = window.grab().toImage()
            comp = QImage(img.size(), QImage.Format.Format_RGB32)
            p = QPainter(comp)
            g = QLinearGradient(0, 0, 0, comp.height())
            g.setColorAt(0, QColor("#e4ecdf")); g.setColorAt(1, QColor("#c2d0c3"))
            p.fillRect(comp.rect(), g)
            p.drawImage(0, 0, img)
            p.setPen(QColor("#233039")); p.setFont(QFont(family, 14, QFont.Weight.Bold))
            p.drawText(QPoint(14, 30), label)
            p.end()
            comp.save(str(out / f"{name}.png"))
            return comp

        class FixedClock:
            """Deterministic replacement for the widget's QElapsedTimer."""
            def __init__(self):
                self.now = 10_000
            def elapsed(self):
                return self.now

        clock = FixedClock()
        frames: list[QImage] = []

        # 1) crossfade neutral -> happy
        sprite.set_idle_animation_enabled(False)
        window.set_sprite(str(args.sprite_a))
        window.add_message("（离线动效采样）先是平静的表情。", char_name="小芽")
        sprite._hop_ms = 0
        sprite._clock = clock
        window.set_sprite(str(args.sprite_b))        # fade starts at clock.now
        fade_start = clock.now
        for t in (0, 60, 120, 200):
            clock.now = fade_start + t
            frames.append(grab(f"crossfade-{t:03d}ms", f"crossfade {t}ms  p={sprite.fade_progress():.2f}"))
        sprite._previous_fitted = None

        # 2) speak hop
        sprite.play_speak_hop()
        hop_start = clock.now
        for t in (0, 100, 180, 260):
            clock.now = hop_start + t
            frames.append(grab(f"hop-{t:03d}ms", f"hop {t}ms  dy={sprite.hop_offset():.1f}px"))
        sprite._hop_ms = 0

        # 3) idle breathing extremes
        sprite.set_idle_animation_enabled(True)
        period = motion.IDLE_BREATH_PERIOD
        for name, frac in (("breath-peak", 0.25), ("breath-trough", 0.75)):
            clock.now = int(period * frac)
            frames.append(grab(name, f"{name}  dy={sprite.idle_offset():.1f}px"))

        # 4) dialogue: typewriter mid-way, completed with continue indicator, thinking dots
        label = window.current_message_label
        label._clock = clock
        sprite.set_idle_animation_enabled(False)
        line = "今天也辛苦啦。要不要听我说说下午在图书馆发现的那本旧书？"
        window.add_message(line, char_name="小芽")
        sprite._hop_ms = 0
        reveal_start = clock.now
        total = motion.typewriter_duration_ms(len(line))
        for frac, name in ((0.35, "type-35pct"), (1.01, "type-done")):
            clock.now = reveal_start + int(total * frac)
            if frac > 1:
                label._on_frame()
            frames.append(grab(name, f"{name}  shown={len(label.visible_text())}/{len(line)}  ▼={label.indicator_visible()}"))
        window.add_message("在吗？想问你点事。", is_user=True)
        window.set_active_character_name("小芽")
        window.set_waiting_for_reply(True)
        clock.now = motion.THINKING_DOT_INTERVAL * 2
        frames.append(grab("thinking", f"thinking  dots={label.thinking_dot_count()}"))
        window.set_waiting_for_reply(False)

        # contact sheet (bottom 55% of each frame, where the action is)
        cols = 4
        crop_top = int(args.height * 0.0)
        tw, th = args.width // 2, (args.height - crop_top) // 2
        rows = (len(frames) + cols - 1) // cols
        sheet = QImage(cols * tw, rows * th, QImage.Format.Format_RGB32)
        sheet.fill(QColor("#ffffff"))
        p = QPainter(sheet)
        for i, f in enumerate(frames):
            scaled = f.copy(0, crop_top, f.width(), f.height() - crop_top).scaled(tw, th, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            p.drawImage((i % cols) * tw, (i // cols) * th, scaled)
        p.end()
        sheet.save(str(out / "motion-sheet.png"))
        window.close()
        print(f"ok frames={len(frames)} out={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
