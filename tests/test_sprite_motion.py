"""立绘动效：交叉淡化、说话轻跳、待机呼吸，以及“减少动效”开关。"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPixmap, QRegion
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ui import motion
from ui.chat_ui.sprite_widget import SpriteWidget


class FixedClock:
    def __init__(self, now=10_000):
        self.now = now

    def elapsed(self):
        return self.now


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def sprite_files(tmp_path):
    paths = []
    for name, color in (("a.png", "red"), ("b.png", "blue")):
        pixmap = QPixmap(80, 120)
        pixmap.fill(color)
        path = tmp_path / name
        assert pixmap.save(str(path))
        paths.append(str(path))
    return paths


@pytest.fixture(autouse=True)
def restore_motion():
    yield
    motion.set_reduced_motion(False)


def make_sprite(clock):
    sprite = SpriteWidget()
    sprite.resize(QSize(320, 240))
    sprite._clock = clock
    return sprite


def test_first_sprite_appears_without_crossfade(app, sprite_files):
    sprite = make_sprite(FixedClock())

    assert sprite.set_sprite(sprite_files[0]) is True
    assert sprite.fade_progress() == 1.0
    assert sprite._previous_fitted is None


def test_changing_sprite_crossfades_over_base_duration(app, sprite_files):
    clock = FixedClock()
    sprite = make_sprite(clock)
    sprite.set_sprite(sprite_files[0])

    sprite.set_sprite(sprite_files[1])

    assert sprite._previous_fitted is not None
    assert sprite.fade_progress() == pytest.approx(0.0)
    clock.now += motion.BASE // 2
    assert 0.3 < sprite.fade_progress() < 0.7
    clock.now += motion.BASE
    assert sprite.fade_progress() == 1.0


def test_crossfade_frame_is_cleared_after_it_finishes(app, sprite_files):
    clock = FixedClock()
    sprite = make_sprite(clock)
    sprite.set_sprite(sprite_files[0])
    sprite.set_sprite(sprite_files[1])

    clock.now += motion.BASE + 1
    sprite._on_frame()

    assert sprite._previous_fitted is None


def test_speak_hop_rises_and_returns_to_rest(app, sprite_files):
    clock = FixedClock()
    sprite = make_sprite(clock)
    sprite.set_sprite(sprite_files[0])

    sprite.play_speak_hop()
    offsets = []
    for _ in range(0, motion.SPEAK_HOP_MS + 1, 20):
        offsets.append(sprite.hop_offset())
        clock.now += 20

    assert offsets[0] == pytest.approx(0.0)
    assert max(offsets) == pytest.approx(motion.SPEAK_HOP_PX, rel=0.05)
    assert offsets[-1] == pytest.approx(0.0)


def test_speak_hop_needs_a_sprite(app):
    sprite = make_sprite(FixedClock())

    sprite.play_speak_hop()

    assert sprite.hop_offset() == 0.0


def test_idle_breathing_stays_within_amplitude(app, sprite_files):
    clock = FixedClock(0)
    sprite = make_sprite(clock)
    sprite.set_sprite(sprite_files[0])

    samples = []
    for t in range(0, motion.IDLE_BREATH_PERIOD, 100):
        clock.now = t
        samples.append(sprite.idle_offset())

    assert max(samples) == pytest.approx(motion.IDLE_BREATH_PX, rel=0.05)
    assert min(samples) == pytest.approx(-motion.IDLE_BREATH_PX, rel=0.05)


def test_reduced_motion_disables_all_sprite_motion(app, sprite_files):
    motion.set_reduced_motion(True)
    clock = FixedClock()
    sprite = make_sprite(clock)
    sprite.set_sprite(sprite_files[0])

    sprite.set_sprite(sprite_files[1])
    sprite.play_speak_hop()

    assert sprite._previous_fitted is None
    assert sprite.fade_progress() == 1.0
    assert sprite.hop_offset() == 0.0
    assert sprite.idle_offset() == 0.0


def test_frame_timer_only_runs_while_visible_and_animating(app, sprite_files):
    sprite = make_sprite(FixedClock())
    sprite.set_sprite(sprite_files[0])
    assert not sprite.is_animating()  # 未显示时不跑

    sprite.show()
    try:
        assert sprite.is_animating()  # 显示后呼吸
        sprite.set_idle_animation_enabled(False)
        assert not sprite.is_animating()
    finally:
        sprite.hide()
    assert not sprite.is_animating()


def test_character_line_triggers_hop_but_user_and_system_lines_do_not(app, sprite_files):
    from ui.chat_ui.chat_ui import ChatUIWindow

    window = ChatUIWindow()
    try:
        window.set_sprite(sprite_files[0])
        sprite = window.sprite_widget
        # 不给 Qt 对象打实例级猴子补丁（会让闭包挂在 shiboken 包装器上，解释器回收时易崩）；
        # 直接观察轻跳状态。
        sprite._hop_ms = 0

        window.add_message("你好", is_user=True)
        window.add_message("系统提示", char_name="系统")
        window.add_message("旁白", char_name="旁白")
        assert sprite._hop_ms == 0

        window.add_message("欢迎回来", char_name="诺艾尔")
        assert sprite._hop_ms == motion.SPEAK_HOP_MS
    finally:
        window.close()


@pytest.fixture
def clickable_window(app, tmp_path):
    from ui.chat_ui.chat_ui import ChatUIWindow

    path = tmp_path / "sprite-with-transparent-margins.png"
    image = QImage(80, 120, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.fillRect(20, 10, 40, 100, Qt.GlobalColor.red)
    painter.end()
    assert image.save(str(path))
    window = ChatUIWindow()
    sprite = window.sprite_widget
    sprite._clock = FixedClock()
    sprite.set_idle_animation_enabled(False)
    window.set_sprite(str(path))
    window.show()
    app.processEvents()
    yield window
    window.close()
    window.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def _click_at(window, point, button=Qt.MouseButton.LeftButton):
    # Use the real topmost child, so overlay interception and event propagation are covered.
    target = window.childAt(point) or window
    QTest.mouseClick(target, button, pos=target.mapFrom(window, point))


@pytest.mark.parametrize("overlay_visible", [True, False])
def test_clicking_sprite_bounces_with_and_without_chat_overlay(clickable_window, overlay_visible):
    window = clickable_window
    motion.set_reduced_motion(True)
    window._set_ui_visible(overlay_visible)
    motion.set_reduced_motion(False)
    sprite = window.sprite_widget
    _click_at(window, QPoint(window.width() // 2, 250))

    assert sprite._hop_ms == motion.CLICK_BOUNCE_MS
    sprite._clock.now += int(motion.CLICK_BOUNCE_MS * 0.4)
    assert sprite.hop_offset() == pytest.approx(motion.CLICK_BOUNCE_PX)
    sprite._clock.now += motion.CLICK_BOUNCE_MS
    sprite._on_frame()
    assert sprite.hop_offset() == 0
    assert sprite.click_scale() == 1
    assert not sprite.is_animating()


def test_click_ignores_transparent_pixels_and_ui_surfaces(clickable_window):
    window = clickable_window
    sprite = window.sprite_widget
    # Stage margin and transparent pixels inside the fitted sprite's bounding rectangle.
    fitted_origin = sprite._anchor(sprite.pixmap()).toPoint()
    inside_transparent = sprite.mapTo(window, fitted_origin + QPoint(5, 100))
    for point in (QPoint(40, 250), inside_transparent,
                  QPoint(window.width() // 2, 30), QPoint(window.width() // 2, window.height() - 95)):
        _click_at(window, point)
        assert sprite._hop_ms == 0

    requested = []
    window.settings_requested.connect(lambda: requested.append(True))
    QTest.mouseClick(window.settings_btn, Qt.MouseButton.LeftButton)
    assert requested == [True]
    assert sprite._hop_ms == 0


@pytest.mark.parametrize("button", [Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton])
def test_sprite_bounce_requires_left_click(clickable_window, button):
    _click_at(clickable_window, QPoint(clickable_window.width() // 2, 250), button)
    assert clickable_window.sprite_widget._hop_ms == 0


def test_sprite_at_top_of_window_is_clickable_between_controls(clickable_window, sprite_files):
    window = clickable_window
    window.set_sprite(sprite_files[0])
    window.sprite_widget._previous_fitted = None
    _click_at(window, QPoint(window.width() // 2, 30))
    assert window.sprite_widget._hop_ms == motion.CLICK_BOUNCE_MS


def test_dragging_sprite_still_moves_window_without_bouncing(clickable_window):
    window = clickable_window
    point = QPoint(window.width() // 2, 250)
    target = window.childAt(point)
    origin = window.pos()
    global_press = window.mapToGlobal(point)
    delta = QPoint(QApplication.startDragDistance() + 30, 20)
    QTest.mousePress(target, Qt.MouseButton.LeftButton, pos=target.mapFrom(window, point))
    event = QMouseEvent(QEvent.Type.MouseMove, QPointF(point + delta), QPointF(global_press + delta),
                        Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(window, event)
    assert window.pos() == origin + delta
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=point)
    assert window.sprite_widget._hop_ms == 0
    assert window._drag_pos is None


def test_repeated_clicks_and_speaking_continue_from_current_offset(clickable_window):
    window = clickable_window
    sprite = window.sprite_widget
    point = QPoint(window.width() // 2, 250)
    _click_at(window, point)
    sprite._clock.now += 80
    before = sprite.hop_offset()
    scale_before = sprite.click_scale()
    assert before > 0
    _click_at(window, point)
    assert sprite.hop_offset() == pytest.approx(before)
    assert sprite.click_scale() == pytest.approx(scale_before)
    sprite._clock.now += 40
    before_speaking = sprite.hop_offset()
    sprite.play_speak_hop()
    assert sprite.hop_offset() == pytest.approx(before_speaking)
    assert sprite._hop_ms == motion.SPEAK_HOP_MS


def test_click_bounce_respects_live_reduced_motion_and_empty_sprite(clickable_window):
    window = clickable_window
    sprite = window.sprite_widget
    point = QPoint(window.width() // 2, 250)
    _click_at(window, point)
    assert sprite._hop_ms > 0
    motion.set_reduced_motion(True)
    sprite.refresh_motion_preferences()
    assert sprite.hop_offset() == 0
    assert sprite.click_scale() == 1
    assert not sprite.is_animating()
    _click_at(window, point)
    assert sprite._hop_ms == 0

    motion.set_reduced_motion(False)
    sprite._source_pixmap = None
    sprite.clear()
    _click_at(window, point)
    assert sprite._hop_ms == 0


def test_click_scale_compresses_rebounds_and_returns_to_rest(clickable_window):
    sprite = clickable_window.sprite_widget
    sprite.play_click_bounce()
    start = sprite._clock.now
    assert sprite.click_scale() == pytest.approx(1)
    sprite._clock.now = start + round(motion.CLICK_BOUNCE_MS * motion.CLICK_SCALE_COMPRESS_AT)
    assert sprite.click_scale() == pytest.approx(motion.CLICK_SCALE_COMPRESS, abs=0.00001)
    sprite._clock.now = start + round(motion.CLICK_BOUNCE_MS * motion.CLICK_SCALE_REBOUND_AT)
    assert sprite.click_scale() == pytest.approx(motion.CLICK_SCALE_REBOUND, abs=0.00001)
    sprite._clock.now = start + motion.CLICK_BOUNCE_MS
    sprite._on_frame()
    assert sprite.click_scale() == 1
    assert not sprite.is_animating()


def test_speaking_does_not_reset_or_end_click_scaling_early(clickable_window):
    sprite = clickable_window.sprite_widget
    sprite.play_click_bounce()
    sprite._clock.now += 20
    before = sprite.click_scale()
    sprite.play_speak_hop()
    assert sprite.click_scale() == pytest.approx(before)
    sprite._clock.now += motion.SPEAK_HOP_MS + 1
    sprite._on_frame()
    assert sprite._hop_ms == 0
    assert sprite.click_scale() != 1
    assert sprite.is_animating()
    sprite._clock.now += motion.CLICK_BOUNCE_MS
    sprite._on_frame()
    assert sprite.click_scale() == 1
    assert not sprite.is_animating()


def test_fading_out_full_height_sprite_does_not_cause_scale_jump(app):
    sprite = make_sprite(FixedClock(0))
    sprite.set_idle_animation_enabled(False)
    old = QPixmap(80, 120)
    old.fill(Qt.GlobalColor.red)
    sprite._source_pixmap = old
    sprite._update_display()
    previous = sprite.pixmap()
    image = QImage(80, 120, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.fillRect(20, 30, 40, 80, Qt.GlobalColor.blue)
    painter.end()
    sprite._source_pixmap = QPixmap.fromImage(image)
    sprite._update_display()
    sprite._previous_fitted = previous
    sprite._fade_start = 0
    sprite._fade_ms = motion.BASE
    sprite.play_click_bounce()
    before = sprite.click_scale(motion.BASE - 1)
    after = sprite.click_scale(motion.BASE)
    assert abs(before - after) < 0.0004


@pytest.mark.parametrize("dpr", [1, 2])
@pytest.mark.parametrize("phase", [motion.CLICK_SCALE_COMPRESS_AT, motion.CLICK_SCALE_REBOUND_AT])
def test_scaled_sprite_hit_test_matches_painted_pixels(app, dpr, phase):
    sprite = make_sprite(FixedClock())
    sprite.resize(320, 400)
    sprite.set_idle_animation_enabled(False)
    image = QImage(320 * dpr, 400 * dpr, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.fillRect(40 * dpr, 40 * dpr, 240 * dpr, 320 * dpr, Qt.GlobalColor.red)
    painter.end()
    source = QPixmap.fromImage(image)
    source.setDevicePixelRatio(dpr)
    sprite._source_pixmap = source
    sprite.show()
    app.processEvents()
    sprite.setPixmap(source)
    try:
        sprite.play_click_bounce()
        sprite._clock.now += round(motion.CLICK_BOUNCE_MS * phase)
        rendered = sprite.grab().toImage()
        bounds = QRegion(QPixmap.fromImage(rendered).mask()).boundingRect()
        center = bounds.center()
        for point in (center, QPoint(center.x(), bounds.top() + 2),
                      QPoint(center.x(), bounds.top() - 2), QPoint(bounds.left() - 2, center.y()),
                      QPoint(bounds.right() + 2, center.y())):
            assert sprite.hit_test(QPointF(point) + QPointF(0.5, 0.5)) == (rendered.pixelColor(point).alpha() > 16)
    finally:
        sprite.close()
        app.processEvents()


@pytest.mark.parametrize("dimensions", [(80, 120), (1200, 200)])
def test_scale_rebound_keeps_full_height_and_wide_art_in_bounds(app, dimensions):
    sprite = make_sprite(FixedClock())
    sprite.set_idle_animation_enabled(False)
    source = QPixmap(*dimensions)
    source.fill(Qt.GlobalColor.red)
    sprite._source_pixmap = source
    sprite.show()
    app.processEvents()
    try:
        sprite.play_click_bounce()
        start = sprite._clock.now
        for t in range(0, motion.CLICK_BOUNCE_MS, 16):
            sprite._clock.now = start + t
            rendered = sprite.grab().toImage()
            bounds = QRegion(QPixmap.fromImage(rendered).mask()).boundingRect()
            scale = sprite.click_scale()
            assert abs(bounds.width() - sprite.pixmap().width() * scale) <= 2
            assert abs(bounds.height() - sprite.pixmap().height() * scale) <= 2
    finally:
        sprite.close()
        app.processEvents()


def test_sprite_timer_uses_precise_short_frames_then_returns_to_idle(clickable_window):
    sprite = clickable_window.sprite_widget
    sprite.set_idle_animation_enabled(True)
    assert sprite._frame_timer.interval() == motion.SPRITE_IDLE_FRAME_MS
    sprite.play_click_bounce()
    assert sprite._frame_timer.interval() == motion.SPRITE_ACTIVE_FRAME_MS
    assert sprite._frame_timer.timerType() == Qt.TimerType.PreciseTimer
    sprite._clock.now += motion.CLICK_BOUNCE_MS + 1
    sprite._on_frame()
    assert sprite._frame_timer.interval() == motion.SPRITE_IDLE_FRAME_MS
    assert sprite._frame_timer.timerType() == Qt.TimerType.CoarseTimer
    assert sprite.is_animating()  # Only the gentle idle motion remains.
    sprite.hide()
    assert not sprite.is_animating()


def test_sprite_repaint_covers_previous_and_new_positions_without_full_window(app, clickable_window):
    class PaintRegions(QObject):
        def __init__(self, parent):
            super().__init__(parent)
            self.regions = []

        def eventFilter(self, watched, event):
            if event.type() == QEvent.Type.Paint:
                self.regions.append(event.region().boundingRect())
            return False

    sprite = clickable_window.sprite_widget
    recorder = PaintRegions(sprite)
    sprite.installEventFilter(recorder)
    sprite.play_click_bounce()
    start = sprite._clock.now
    sprite._clock.now = start + round(motion.CLICK_BOUNCE_MS * motion.CLICK_SCALE_REBOUND_AT)
    sprite._on_frame()
    sprite._frame_timer.stop()
    app.processEvents()
    previous_bounds = QRegion(sprite.grab().mask()).boundingRect()
    recorder.regions.clear()
    sprite._clock.now = start + motion.CLICK_BOUNCE_MS
    sprite._on_frame()
    sprite._frame_timer.stop()
    app.processEvents()
    assert recorder.regions
    repainted = recorder.regions[-1]
    current_bounds = QRegion(sprite.grab().mask()).boundingRect()
    assert repainted.contains(previous_bounds)
    assert repainted.contains(current_bounds)
    assert repainted.width() < sprite.width() * 0.7


def test_queued_sprite_frame_stays_inside_dirty_region_if_paint_is_delayed(app, clickable_window):
    class PaintRegions(QObject):
        def __init__(self, parent):
            super().__init__(parent)
            self.last = None

        def eventFilter(self, watched, event):
            if event.type() == QEvent.Type.Paint:
                self.last = event.region().boundingRect()
            return False

    sprite = clickable_window.sprite_widget
    recorder = PaintRegions(sprite)
    sprite.installEventFilter(recorder)
    sprite.play_click_bounce()
    start = sprite._clock.now
    app.processEvents()
    sprite._clock.now = start + round(motion.CLICK_BOUNCE_MS * motion.CLICK_SCALE_COMPRESS_AT)
    sprite._on_frame()
    sprite._frame_timer.stop()
    sprite._clock.now = start + round(motion.CLICK_BOUNCE_MS * motion.CLICK_SCALE_REBOUND_AT)
    app.processEvents()  # Paint the rebound pose into a region requested during compression.
    repainted = recorder.last
    visible = QRegion(sprite.grab().mask()).boundingRect()
    assert repainted.contains(visible)


def test_click_bounds_keep_faint_alpha_pixels(app):
    sprite = make_sprite(FixedClock())
    sprite.set_idle_animation_enabled(False)
    image = QImage(80, 120, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    image.setPixelColor(0, 0, QColor(255, 0, 0, 1))
    image.setPixelColor(79, 119, QColor(255, 0, 0, 1))
    sprite._source_pixmap = QPixmap.fromImage(image)
    sprite._update_display()
    sprite.play_click_bounce()
    sprite.click_scale()
    bounds = sprite._scale_bounds[sprite.pixmap().cacheKey()]
    assert bounds.left() == 0 and bounds.top() == 0
    assert bounds.width() == sprite.pixmap().width()
    assert bounds.height() == sprite.pixmap().height()
    sprite.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
