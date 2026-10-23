"""立绘舞台控件：交叉淡化换表情、待机呼吸、说话轻跳、点击轻弹。

仍继承 QLabel 并通过 setPixmap 保存“当前适配后的立绘”，以保持原有 API
（pixmap() / set_sprite / set_scale / _source_pixmap / _scale / _update_display）。

实现要点：
- 不用 QGraphicsOpacityEffect（透明无边框窗口里代价高），在 paintEvent 中
  直接按进度以不同不透明度绘制新旧两帧并整体偏移。
- 所有动效共用一个 QTimer，进度由时间戳计算（掉帧不漂移），只在有动效时运行。
  不使用 QVariantAnimation：在 PySide6 6.8 下，独立创建的此类控件在解释器
  回收阶段会触发段错误（离线测试中稳定复现）。
"""

from __future__ import annotations

import math
import os

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QPainter, QPixmap, QRegion
from PySide6.QtWidgets import QLabel, QSizePolicy

from ui import motion

def _ease_in_out_sine(t: float) -> float:
    return -(math.cos(math.pi * t) - 1.0) / 2.0


def _hop_curve(t: float) -> float:
    """0→1→0：前 40% 快速上升（out-quad），后 60% 缓落（in-out-sine）。"""
    if t <= 0.0 or t >= 1.0:
        return 0.0
    if t < 0.4:
        u = t / 0.4
        return 1.0 - (1.0 - u) * (1.0 - u)
    u = (t - 0.4) / 0.6
    return 1.0 - _ease_in_out_sine(u)


class SpriteWidget(QLabel):
    """立绘显示区域 — 透明背景，自适应控件高度。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)
        self.setMinimumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self._source_pixmap: QPixmap | None = None
        self._scale = 1.0

        self._clock = QElapsedTimer()
        self._clock.start()

        # 交叉淡化：_previous_fitted 是旧帧；在 [_fade_start, _fade_start+_fade_ms] 内新帧渐显。
        self._previous_fitted: QPixmap | None = None
        self._fade_start = 0
        self._fade_ms = 0

        # 说话轻跳
        self._hop_start = 0
        self._hop_ms = 0
        self._hop_from = 0.0
        self._hop_px = motion.SPEAK_HOP_PX

        self._click_scale_start = 0
        self._click_scale_ms = 0
        self._click_scale_from = 1.0
        self._scale_bounds = {}
        self._last_painted_bounds = QRectF()

        self._idle_enabled = True
        self._frame_timer = QTimer(self)
        self._frame_timer.setInterval(motion.SPRITE_IDLE_FRAME_MS)
        self._frame_timer.timeout.connect(self._on_frame)

    # ── 公共 API ─────────────────────────────────────

    def clear_sprite(self) -> None:
        """Drop the image and all animation state immediately on character change."""
        self._frame_timer.stop()
        self._source_pixmap = None
        self._previous_fitted = None
        self._fade_ms = 0
        self._hop_ms = 0
        self._hop_from = 0.0
        self._click_scale_ms = 0
        self._click_scale_from = 1.0
        self._scale_bounds.clear()
        self._last_painted_bounds = QRectF()
        self.clear()
        self.update()

    def set_sprite(self, image_path: str, scale: float = 1.0):
        """加载并显示立绘；若已有立绘则交叉淡化过渡。"""
        if not image_path or not os.path.exists(image_path):
            return False
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return False
        old_fitted = self.pixmap()
        had_sprite = self._source_pixmap is not None and old_fitted is not None and not old_fitted.isNull()
        self._scale = scale
        self._source_pixmap = pixmap
        self._update_display()
        fade_ms = motion.duration(motion.BASE)
        if had_sprite and fade_ms > 0:
            self._previous_fitted = old_fitted
            self._fade_start = self._clock.elapsed()
            self._fade_ms = fade_ms
        else:
            self._previous_fitted = None
            self._fade_ms = 0
        self._sync_timer()
        self.update()
        return True

    def set_scale(self, scale: float) -> None:
        """设置相对适配尺寸的缩放倍率（0.1–1.0），立即重绘。"""
        self._scale = scale
        self._previous_fitted = None
        self._update_display()

    def play_speak_hop(self) -> None:
        """新台词出现时轻跳一下。减少动效时不跳。"""
        self._start_hop(motion.SPEAK_HOP_MS, motion.SPEAK_HOP_PX)

    def play_click_bounce(self) -> None:
        """点击反馈；与说话共用位移通道，连点时从当前位置接上。"""
        if self._source_pixmap is None or motion.reduced_motion():
            return
        self._click_scale_from = self.click_scale()
        self._click_scale_start = self._clock.elapsed()
        self._click_scale_ms = motion.CLICK_BOUNCE_MS
        self._start_hop(motion.CLICK_BOUNCE_MS, motion.CLICK_BOUNCE_PX)

    def _start_hop(self, duration_ms: int, height: float) -> None:
        if self._source_pixmap is None or motion.reduced_motion():
            return
        self._hop_from = self.hop_offset()
        self._hop_px = height
        self._hop_start = self._clock.elapsed()
        self._hop_ms = duration_ms
        self._sync_timer()
        self._request_frame()

    def set_idle_animation_enabled(self, enabled: bool) -> None:
        self._idle_enabled = bool(enabled)
        self._sync_timer()
        self.update()

    def refresh_motion_preferences(self) -> None:
        if motion.reduced_motion():
            self._previous_fitted = None
            self._hop_ms = 0
            self._click_scale_ms = 0
        self._sync_timer()
        self.update()

    def is_animating(self) -> bool:
        return self._frame_timer.isActive()

    # ── 动画状态（纯计算，便于测试与截图采样）──────────

    def fade_progress(self, now_ms: int | None = None) -> float:
        if self._previous_fitted is None or self._fade_ms <= 0:
            return 1.0
        now = self._clock.elapsed() if now_ms is None else now_ms
        t = (now - self._fade_start) / self._fade_ms
        return 1.0 if t >= 1.0 else _ease_in_out_sine(max(0.0, t))

    def hop_offset(self, now_ms: int | None = None) -> float:
        if self._hop_ms <= 0:
            return 0.0
        now = self._clock.elapsed() if now_ms is None else now_ms
        t = max(0.0, (now - self._hop_start) / self._hop_ms)
        if t < 0.4:
            return self._hop_from + (self._hop_px - self._hop_from) * _hop_curve(t)
        return _hop_curve(t) * self._hop_px

    def idle_offset(self, now_ms: int | None = None) -> float:
        if not self._idle_active():
            return 0.0
        now = self._clock.elapsed() if now_ms is None else now_ms
        phase = (now % motion.IDLE_BREATH_PERIOD) / motion.IDLE_BREATH_PERIOD
        return math.sin(phase * 2 * math.pi) * motion.IDLE_BREATH_PX

    def click_scale(self, now_ms: int | None = None) -> float:
        """脚底居中的轻缩→回弹→归位；连点从当前缩放接续。"""
        if self._click_scale_ms <= 0 or motion.reduced_motion():
            return 1.0
        now = self._clock.elapsed() if now_ms is None else now_ms
        t = max(0.0, (now - self._click_scale_start) / self._click_scale_ms)
        if t >= 1.0:
            return 1.0
        compress_at = motion.CLICK_SCALE_COMPRESS_AT
        rebound_at = motion.CLICK_SCALE_REBOUND_AT
        if t < compress_at:
            start, end, u = self._click_scale_from, motion.CLICK_SCALE_COMPRESS, t / compress_at
        elif t < rebound_at:
            start, end = motion.CLICK_SCALE_COMPRESS, motion.CLICK_SCALE_REBOUND
            u = (t - compress_at) / (rebound_at - compress_at)
        else:
            start, end = motion.CLICK_SCALE_REBOUND, 1.0
            u = (t - rebound_at) / (1.0 - rebound_at)
        desired = start + (end - start) * _ease_in_out_sine(u)
        return self._scale_limit(now, desired)

    # ── 内部 ─────────────────────────────────────────

    def _idle_active(self) -> bool:
        return self._idle_enabled and not motion.reduced_motion() and self._source_pixmap is not None

    def _transient_active(self) -> bool:
        now = self._clock.elapsed()
        fading = self._previous_fitted is not None and now - self._fade_start < self._fade_ms
        hopping = self._hop_ms > 0 and now - self._hop_start < self._hop_ms
        scaling = self._click_scale_ms > 0 and now - self._click_scale_start < self._click_scale_ms
        return fading or hopping or scaling

    def _sync_timer(self) -> None:
        active = self._transient_active()
        interval = motion.SPRITE_ACTIVE_FRAME_MS if active else motion.SPRITE_IDLE_FRAME_MS
        timer_type = Qt.TimerType.PreciseTimer if active else Qt.TimerType.CoarseTimer
        if self._frame_timer.timerType() != timer_type:
            self._frame_timer.setTimerType(timer_type)
        if self._frame_timer.interval() != interval:
            self._frame_timer.setInterval(interval)
        wanted = self.isVisible() and (self._idle_active() or active)
        if wanted and not self._frame_timer.isActive():
            self._frame_timer.start()
        elif not wanted and self._frame_timer.isActive():
            self._frame_timer.stop()

    def _on_frame(self) -> None:
        now = self._clock.elapsed()
        if self._previous_fitted is not None and now - self._fade_start >= self._fade_ms:
            self._previous_fitted = None
        if self._hop_ms > 0 and now - self._hop_start >= self._hop_ms:
            self._hop_ms = 0
        if self._click_scale_ms > 0 and now - self._click_scale_start >= self._click_scale_ms:
            self._click_scale_ms = 0
        self._request_frame(now)
        self._sync_timer()

    def _update_display(self):
        if self._source_pixmap is None:
            return
        fitted = self._source_pixmap.scaled(
            max(1, self.width()),
            max(1, self.height()),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scale = max(0.1, min(1.0, self._scale))
        if scale < 1.0:
            fitted = fitted.scaled(
                max(1, int(fitted.width() * scale)),
                max(1, int(fitted.height() * scale)),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self.setPixmap(fitted)
        self._scale_bounds.clear()

    def _anchor(self, pixmap: QPixmap) -> QPointF:
        """底部居中对齐（与原 QLabel AlignBottom|AlignHCenter 一致）。"""
        dpr = pixmap.devicePixelRatio() or 1.0
        return QPointF((self.width() - pixmap.width() / dpr) / 2.0, self.height() - pixmap.height() / dpr)

    def _paint_offset(self, now_ms: int) -> QPointF:
        lift = self.idle_offset(now_ms) + self.hop_offset(now_ms)
        return QPointF(0.0, motion.IDLE_BREATH_PX - lift if self._idle_active() else -lift)

    def _paint_bounds(self, now_ms: int, offset=None, scale=None) -> QRectF:
        """可见帧的包围框；未提取过 alpha 边界时使用完整图框，避免启动扫描。"""
        offset = self._paint_offset(now_ms) if offset is None else offset
        scale = self.click_scale(now_ms) if scale is None else scale
        pivot = QPointF(self.width() / 2.0, self.height())
        progress = self.fade_progress(now_ms)
        result = QRectF()
        for pixmap, opacity in ((self.pixmap(), progress), (self._previous_fitted, 1.0 - progress)):
            if pixmap is None or pixmap.isNull() or opacity <= 0:
                continue
            bounds = self._scale_bounds.get(pixmap.cacheKey())
            if bounds is None:
                dpr = pixmap.devicePixelRatio() or 1.0
                bounds = QRectF(0, 0, pixmap.width() / dpr, pixmap.height() / dpr)
            if bounds.isEmpty():
                continue
            bounds = bounds.translated(self._anchor(pixmap))
            transformed = QRectF(
                pivot.x() + offset.x() + (bounds.left() - pivot.x()) * scale,
                pivot.y() + offset.y() + (bounds.top() - pivot.y()) * scale,
                bounds.width() * scale, bounds.height() * scale,
            )
            result = result.united(transformed)
        return result

    def _request_frame(self, now_ms: int | None = None) -> None:
        now = self._clock.elapsed() if now_ms is None else now_ms
        dirty = self._last_painted_bounds.united(self._paint_bounds(now))
        if not dirty.isEmpty():
            # Cover queued-paint delays too: paintEvent may sample a later pose.
            padding = 2 + 2 * motion.IDLE_BREATH_PX
            if self._hop_ms > 0 or self._click_scale_ms > 0:
                scale_travel = max(1 - motion.CLICK_SCALE_COMPRESS, motion.CLICK_SCALE_REBOUND - 1)
                padding += max(motion.CLICK_BOUNCE_PX, self._hop_from, self._hop_px)
                padding += max(self.width() / 2.0, self.height()) * scale_travel
            self.update(dirty.adjusted(-padding, -padding, padding, padding).toAlignedRect())

    def _scale_limit(self, now_ms: int, desired: float) -> float:
        """只在点击时计算并缓存可见图形边界，回弹不把头发或宽图挤出窗口。"""
        pivot = QPointF(self.width() / 2.0, self.height())
        translated = pivot + self._paint_offset(now_ms)
        limits = []
        progress = self.fade_progress(now_ms)
        previous = self._previous_fitted if progress < 1.0 else None
        for pixmap in (self.pixmap(), previous):
            if pixmap is None or pixmap.isNull():
                continue
            limit = desired
            key = pixmap.cacheKey()
            if key not in self._scale_bounds:
                rect = QRegion(pixmap.mask()).boundingRect() if pixmap.hasAlphaChannel() else pixmap.rect()
                dpr = pixmap.devicePixelRatio() or 1.0
                self._scale_bounds[key] = QRectF(rect.x() / dpr, rect.y() / dpr,
                                                rect.width() / dpr, rect.height() / dpr)
            bounds = self._scale_bounds[key].translated(self._anchor(pixmap))
            for distance, space in ((pivot.x() - bounds.left(), translated.x()),
                                    (bounds.right() - pivot.x(), self.width() - translated.x()),
                                    (pivot.y() - bounds.top(), translated.y()),
                                    (bounds.bottom() - pivot.y(), self.height() - translated.y())):
                if distance > 0:
                    limit = min(limit, max(0.1, space / distance))
            limits.append(limit)
        if len(limits) == 2:
            # Release the fading image's constraint continuously, not on the final frame.
            return min(limits[0], limits[0] * progress + limits[1] * (1.0 - progress))
        return limits[0] if limits else desired

    def hit_test(self, position) -> bool:
        """命中当前可见立绘像素，透明边距不算点击角色。"""
        now = self._clock.elapsed()
        offset = self._paint_offset(now)
        scale = self.click_scale(now)
        pivot = QPointF(self.width() / 2.0, self.height())
        position = pivot + (QPointF(position) - pivot - offset) / scale
        progress = self.fade_progress(now)
        frames = [(self.pixmap(), progress)]
        if self._previous_fitted is not None:
            frames.append((self._previous_fitted, 1.0 - progress))
        for pixmap, opacity in frames:
            if pixmap is None or pixmap.isNull() or opacity <= 0.05:
                continue
            origin = self._anchor(pixmap)
            dpr = pixmap.devicePixelRatio() or 1.0
            x = (position.x() - origin.x()) * dpr
            y = (position.y() - origin.y()) * dpr
            if 0 <= x < pixmap.width() and 0 <= y < pixmap.height():
                if pixmap.toImage().pixelColor(int(x), int(y)).alpha() * opacity > 16:
                    return True
        return False

    def paintEvent(self, event):
        current = self.pixmap()
        if current is None or current.isNull():
            return
        now = self._clock.elapsed()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        # 呼吸与轻跳都让角色向上浮动；基线下沉一个呼吸幅度，保证最低点也贴住底边。
        offset = self._paint_offset(now)
        scale = self.click_scale(now)
        self._last_painted_bounds = self._paint_bounds(now, offset, scale)
        pivot = QPointF(self.width() / 2.0, self.height())
        painter.translate(pivot + offset)
        painter.scale(scale, scale)
        painter.translate(-pivot.x(), -pivot.y())
        progress = self.fade_progress(now)
        if self._previous_fitted is not None and progress < 1.0:
            painter.setOpacity(1.0 - progress)
            painter.drawPixmap(self._anchor(self._previous_fitted), self._previous_fitted)
            painter.setOpacity(progress)
        painter.drawPixmap(self._anchor(current), current)
        painter.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._previous_fitted = None
        self._update_display()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._frame_timer.stop()
