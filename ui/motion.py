"""统一的动效参数与“减少动效”开关。

所有聊天窗口动效都从这里取时长/缓动，避免各处散落魔法数字。
开启 reduce motion 后：一次性过渡直接跳到终态，循环动效（呼吸、跳点）停止。
"""

from __future__ import annotations

from dataclasses import dataclass

# ── 时长（毫秒）──────────────────────────────────
FAST = 120        # 悬停、按下等微反馈
BASE = 200        # 淡入淡出、立绘交叉淡化
SLOW = 320        # 面板进入、较大位移
OVERLAY = 160     # 聊天界面展开/收起
PAGE = 200        # 设置页切换
PAGE_SLIDE_PX = 8

# 循环动效
IDLE_BREATH_PERIOD = 4200   # 立绘呼吸一个周期
IDLE_BREATH_PX = 2.0        # 呼吸上下浮动幅度（像素）
SPEAK_HOP_PX = 6.0          # 新台词时立绘轻跳高度
SPEAK_HOP_MS = 260
CLICK_BOUNCE_PX = 10.0     # 点击立绘时的轻弹高度
CLICK_BOUNCE_MS = 320
CLICK_SCALE_COMPRESS = 0.98  # 先轻缩，再略微放大回弹
CLICK_SCALE_REBOUND = 1.012
CLICK_SCALE_COMPRESS_AT = 0.22
CLICK_SCALE_REBOUND_AT = 0.55
SPRITE_ACTIVE_FRAME_MS = 16  # 短动效使用精确定时；结束后恢复低频待机
SPRITE_IDLE_FRAME_MS = 33
ENTRANCE_SLIDE_PX = 8       # 卡片/选项进入时的上滑距离
CONTINUE_BOB_PERIOD = 900   # ▼ 提示上下跳动周期
THINKING_DOT_INTERVAL = 380 # 思考中“…”每帧间隔

# 逐字显示
TYPEWRITER_CPS = 40         # 每秒字符数（默认）
TYPEWRITER_MAX_MS = 4000    # 长台词最多用这么久显示完，避免拖沓


@dataclass
class _MotionState:
    reduced: bool = False
    typewriter: bool = True
    typewriter_cps: int = TYPEWRITER_CPS


_state = _MotionState()


def reduced_motion() -> bool:
    return _state.reduced


def set_reduced_motion(value: bool) -> None:
    _state.reduced = bool(value)


def typewriter_enabled() -> bool:
    return _state.typewriter and not _state.reduced


def set_typewriter(enabled: bool, cps: int | None = None) -> None:
    _state.typewriter = bool(enabled)
    if cps is not None:
        _state.typewriter_cps = max(5, min(200, int(cps)))


def typewriter_cps() -> int:
    return _state.typewriter_cps


def typewriter_duration_ms(char_count: int) -> int:
    """逐字显示整句所需时长：按字速计算，但封顶 TYPEWRITER_MAX_MS。"""
    if char_count <= 0:
        return 0
    return min(TYPEWRITER_MAX_MS, int(char_count * 1000 / typewriter_cps()))


def duration(ms: int) -> int:
    """一次性过渡的实际时长；减少动效时为 0（直接到终态）。"""
    return 0 if _state.reduced else ms


def apply_system_config(system_config) -> None:
    """从 SystemConfig 读取动效偏好；缺字段时保持默认。"""
    set_reduced_motion(getattr(system_config, "reduce_motion", False))
    set_typewriter(
        getattr(system_config, "typewriter_enabled", True),
        getattr(system_config, "typewriter_cps", TYPEWRITER_CPS),
    )
    # Settings can be saved while the chat window is already running.
    try:
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError:
        return
    app = QApplication.instance()
    if app is not None:
        for widget in app.allWidgets():
            refresh = getattr(widget, "refresh_motion_preferences", None)
            if callable(refresh):
                refresh()
            entrance = getattr(widget, "_entrance_group", None)
            if _state.reduced and entrance is not None:
                entrance.setCurrentTime(entrance.duration())


try:
    from PySide6.QtCore import QEasingCurve

    EASE_OUT = QEasingCurve.Type.OutCubic
    EASE_IN_OUT = QEasingCurve.Type.InOutSine
    EASE_HOP = QEasingCurve.Type.OutQuad
except ModuleNotFoundError:  # 纯逻辑测试环境
    EASE_OUT = EASE_IN_OUT = EASE_HOP = None
