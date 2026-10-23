"""台词框文本控件：逐字显示 + 点击补全 + ▼ 续读提示 + 思考中跳点。

DialogueTextLabel 继承 QLabel，text() 始终返回“完整台词”（保持原有调用方与
测试的语义），实际绘制时只画出已显示的前缀。逐字显示期间点击可立即补全。

全部动效共用一个 QTimer，进度按时间戳计算；不使用 QVariantAnimation
（PySide6 6.8 下独立控件持有它会在解释器回收时段错误，见 sprite_widget）。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QTextCharFormat, QTextCursor, QTextDocument, QTextOption,
)
from PySide6.QtWidgets import QLabel, QSizePolicy

from ui import motion

_FRAME_INTERVAL_MS = 33
_INDICATOR_SIZE = 9.0       # ▼ 三角形宽度
_INDICATOR_COLOR = QColor(96, 123, 101, 230)
_DOT_COLOR = QColor(96, 123, 101)


class DialogueTextLabel(QLabel):
    """ADV 台词：逐字显示，点击补全；显示完后右下角 ▼ 轻轻跳动。"""

    reveal_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._full_text = ""
        self._reveal_start = 0
        self._reveal_ms = 0
        self._revealing = False
        self._show_indicator = False
        self._thinking = False

        self._clock = QElapsedTimer()
        self._clock.start()
        self._frame_timer = QTimer(self)
        self._frame_timer.setInterval(_FRAME_INTERVAL_MS)
        self._frame_timer.timeout.connect(self._on_frame)

    # ── 公共 API ─────────────────────────────────────

    def setText(self, text: str) -> None:  # noqa: N802 (Qt naming)
        """立即显示整句（流式追加、清空等场景用）。"""
        self._full_text = text or ""
        self._revealing = False
        self._thinking = False
        self._show_indicator = False
        super().setText(self._full_text)
        self._sync_timer()
        self.update()

    def clear(self) -> None:
        self.setText("")

    def reveal(self, text: str) -> None:
        """逐字显示新台词；关闭逐字显示或减少动效时等同 setText。"""
        self.setText(text)
        duration = motion.typewriter_duration_ms(len(self._full_text)) if motion.typewriter_enabled() else 0
        if duration <= 0:
            self._finish_reveal()
            return
        self._reveal_start = self._clock.elapsed()
        self._reveal_ms = duration
        self._revealing = True
        self._sync_timer()
        self.update()

    def complete_reveal(self) -> bool:
        """补全当前台词。返回 True 表示确实打断了正在进行的逐字显示。"""
        if not self._revealing:
            return False
        self._finish_reveal()
        return True

    def set_thinking(self, thinking: bool) -> None:
        """等待回复时，在台词位置显示跳动的“…”。"""
        thinking = bool(thinking)
        if thinking == self._thinking:
            return
        self._thinking = thinking
        if thinking:
            self._show_indicator = False
        self._sync_timer()
        self.update()

    def is_revealing(self) -> bool:
        return self._revealing

    def is_thinking(self) -> bool:
        return self._thinking

    def indicator_visible(self) -> bool:
        return self._show_indicator and not self._thinking

    def visible_text(self, now_ms: int | None = None) -> str:
        if self._thinking and not self._full_text:
            return ""
        if not self._revealing:
            return self._full_text
        now = self._clock.elapsed() if now_ms is None else now_ms
        progress = (now - self._reveal_start) / self._reveal_ms if self._reveal_ms else 1.0
        if progress >= 1.0:
            return self._full_text
        return self._full_text[: max(0, int(len(self._full_text) * progress))]

    def indicator_offset(self, now_ms: int | None = None) -> float:
        if motion.reduced_motion():
            return 0.0
        now = self._clock.elapsed() if now_ms is None else now_ms
        phase = (now % motion.CONTINUE_BOB_PERIOD) / motion.CONTINUE_BOB_PERIOD
        return (1.0 - math.cos(phase * 2 * math.pi)) * 1.25  # 0..2.5px 向下

    def thinking_dot_count(self, now_ms: int | None = None) -> int:
        """1→2→3 循环；减少动效时固定 3 个。"""
        if motion.reduced_motion():
            return 3
        now = self._clock.elapsed() if now_ms is None else now_ms
        return 1 + (now // motion.THINKING_DOT_INTERVAL) % 3

    # ── 内部 ─────────────────────────────────────────

    def _finish_reveal(self) -> None:
        was_revealing = self._revealing
        self._revealing = False
        self._show_indicator = bool(self._full_text)
        self._sync_timer()
        self.update()
        if was_revealing or self._full_text:
            self.reveal_finished.emit()

    def _needs_frames(self) -> bool:
        if not self.isVisible() or motion.reduced_motion():
            return False
        if self._revealing or self._thinking:
            return True
        return self._show_indicator and not motion.reduced_motion()

    def _sync_timer(self) -> None:
        wanted = self._needs_frames()
        if wanted and not self._frame_timer.isActive():
            self._frame_timer.start()
        elif not wanted and self._frame_timer.isActive():
            self._frame_timer.stop()

    def _on_frame(self) -> None:
        if self._revealing and self._clock.elapsed() - self._reveal_start >= self._reveal_ms:
            self._finish_reveal()
            return
        self.update()
        self._sync_timer()

    def refresh_motion_preferences(self) -> None:
        if self._revealing and not motion.typewriter_enabled():
            self._finish_reveal()
        self._sync_timer()
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.complete_reveal():
            event.accept()
            return
        super().mousePressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._frame_timer.stop()

    # ── 绘制 ─────────────────────────────────────────

    def _layout_document(self, width: float, visible_len: int) -> QTextDocument:
        """用完整文本排版、把未显示部分设为透明：逐字过程中换行位置保持稳定，不会“跳行”。"""
        doc = QTextDocument()
        doc.setDefaultFont(self.font())
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        doc.setDefaultTextOption(option)
        doc.setDocumentMargin(0)
        doc.setTextWidth(width)
        doc.setPlainText(self._full_text)

        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.SelectionType.Document)
        shown = QTextCharFormat()
        shown.setForeground(self.palette().color(self.foregroundRole()))
        cursor.mergeCharFormat(shown)
        if visible_len < len(self._full_text):
            cursor.setPosition(visible_len)
            cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
            hidden = QTextCharFormat()
            hidden.setForeground(QColor(0, 0, 0, 0))
            cursor.mergeCharFormat(hidden)
        return doc

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.contentsRect())
        now = self._clock.elapsed()

        if self._thinking and not self._full_text:
            self._paint_thinking_dots(painter, rect, now)
            painter.end()
            return

        doc = self._layout_document(rect.width(), len(self.visible_text(now)))
        painter.translate(rect.topLeft())
        doc.drawContents(painter)
        painter.translate(-rect.topLeft())
        if self.indicator_visible():
            self._paint_indicator(painter, rect, doc, now)
        painter.end()

    def _paint_indicator(self, painter: QPainter, rect: QRectF, doc: QTextDocument, now: int) -> None:
        size = _INDICATOR_SIZE
        # 紧跟在最后一行文字之后（经典 ADV 位置），放不下时换到下一行行首。
        layout = doc.lastBlock().layout()
        last_line = layout.lineAt(layout.lineCount() - 1) if layout and layout.lineCount() else None
        line_height = self.fontMetrics().height()
        if last_line is not None:
            block_top = layout.position().y()
            x = rect.left() + last_line.naturalTextWidth() + 6
            y = rect.top() + block_top + last_line.y() + (last_line.height() - size * 0.8) / 2.0
            if x + size > rect.right():
                x = rect.left()
                y += last_line.height()
        else:
            x = rect.left()
            y = rect.top() + (line_height - size * 0.8) / 2.0
        y += self.indicator_offset(now)
        path = QPainterPath()
        path.moveTo(x, y)
        path.lineTo(x + size, y)
        path.lineTo(x + size / 2.0, y + size * 0.8)
        path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_INDICATOR_COLOR)
        painter.drawPath(path)

    def _paint_thinking_dots(self, painter: QPainter, rect: QRectF, now: int) -> None:
        count = self.thinking_dot_count(now)
        radius = 3.2
        gap = 10.0
        cy = rect.top() + self.fontMetrics().height() / 2.0
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            alpha = 220 if i < count else 60
            color = QColor(_DOT_COLOR)
            color.setAlpha(alpha)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(rect.left() + radius + i * gap, cy), radius, radius)
