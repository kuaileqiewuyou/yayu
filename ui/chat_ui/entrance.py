"""临时内容（资料卡 / 选项 / CG 预览）的进入动效：淡入 + 轻微上滑。

- 透明度效果只在动画期间挂载，结束后立即移除（透明无边框窗口里常驻
  QGraphicsOpacityEffect 会让每次重绘都走离屏合成）。
- 上滑通过临时的上边距实现，不改动控件在布局中的最终位置。
- 动画对象以窗口为 parent（与原有的 overlay 淡入淡出一致），播放完自动删除。
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractAnimation, QParallelAnimationGroup, QPropertyAnimation, QVariantAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

from ui import motion


def play_entrance(widget: QWidget, owner: QWidget) -> QAbstractAnimation | None:
    """让刚加入布局的控件淡入并上滑到位。减少动效时直接显示终态。"""
    duration = motion.duration(motion.SLOW)
    if duration <= 0 or widget.graphicsEffect() is not None:
        return None

    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)

    margins = widget.contentsMargins()
    base_top = margins.top()

    fade = QPropertyAnimation(effect, b"opacity", owner)
    fade.setDuration(duration)
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    fade.setEasingCurve(motion.EASE_OUT)

    slide = QVariantAnimation(owner)
    slide.setDuration(duration)
    slide.setStartValue(float(motion.ENTRANCE_SLIDE_PX))
    slide.setEndValue(0.0)
    slide.setEasingCurve(motion.EASE_OUT)

    def apply_slide(value) -> None:
        m = widget.contentsMargins()
        widget.setContentsMargins(m.left(), base_top + int(round(float(value))), m.right(), m.bottom())

    slide.valueChanged.connect(apply_slide)
    apply_slide(motion.ENTRANCE_SLIDE_PX)

    group = QParallelAnimationGroup(owner)
    widget._entrance_group = group
    group.addAnimation(fade)
    group.addAnimation(slide)

    def finish() -> None:
        widget._entrance_group = None
        m = widget.contentsMargins()
        widget.setContentsMargins(m.left(), base_top, m.right(), m.bottom())
        if widget.graphicsEffect() is effect:
            widget.setGraphicsEffect(None)

    group.finished.connect(finish)
    group.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    return group
