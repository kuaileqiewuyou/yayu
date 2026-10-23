import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QPixmap, QWheelEvent
from PySide6.QtWidgets import QApplication

from ui.chat_ui.chat_ui import ChatUIWindow
from ui.window_chrome import FramelessResizeController


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _mouse_event(etype, local_pos, global_pos, button, buttons):
    return QMouseEvent(
        etype,
        QPointF(local_pos),
        QPointF(global_pos),
        button,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


# ── 命中测试与光标 ─────────────────────────────────────────


def test_edges_at_detects_borders_and_corners(app):
    rect = ChatUIWindow().rect()
    margin = 6
    edges = FramelessResizeController.edges_at
    assert edges(rect, QPoint(2, 300), margin) == Qt.Edge.LeftEdge
    assert edges(rect, QPoint(rect.width() - 2, 300), margin) == Qt.Edge.RightEdge
    assert edges(rect, QPoint(300, 1), margin) == Qt.Edge.TopEdge
    assert edges(rect, QPoint(300, rect.height() - 1), margin) == Qt.Edge.BottomEdge
    corner = edges(rect, QPoint(rect.width() - 1, rect.height() - 1), margin)
    assert corner & Qt.Edge.RightEdge and corner & Qt.Edge.BottomEdge
    assert edges(rect, QPoint(rect.width() // 2, rect.height() // 2), margin) == Qt.Edges(0)


def test_cursor_mapping_for_edges(app):
    cursor = FramelessResizeController.cursor_for_edges
    assert cursor(Qt.Edge.LeftEdge) == Qt.CursorShape.SizeHorCursor
    assert cursor(Qt.Edge.RightEdge) == Qt.CursorShape.SizeHorCursor
    assert cursor(Qt.Edge.TopEdge) == Qt.CursorShape.SizeVerCursor
    assert cursor(Qt.Edge.BottomEdge) == Qt.CursorShape.SizeVerCursor
    assert cursor(Qt.Edge.LeftEdge | Qt.Edge.TopEdge) == Qt.CursorShape.SizeFDiagCursor
    assert cursor(Qt.Edge.RightEdge | Qt.Edge.BottomEdge) == Qt.CursorShape.SizeFDiagCursor
    assert cursor(Qt.Edge.RightEdge | Qt.Edge.TopEdge) == Qt.CursorShape.SizeBDiagCursor
    assert cursor(Qt.Edge.LeftEdge | Qt.Edge.BottomEdge) == Qt.CursorShape.SizeBDiagCursor
    assert cursor(Qt.Edges(0)) is None


# ── 边缘拖拽缩放 ───────────────────────────────────────────


def test_right_edge_drag_resizes_window(app):
    window = ChatUIWindow()
    window.show()
    app.processEvents()
    controller = window._resize_controller
    try:
        start = window.geometry()
        local = QPoint(start.width() - 2, start.height() // 2)
        press = _mouse_event(
            QEvent.Type.MouseButtonPress,
            local,
            window.mapToGlobal(local),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
        )
        assert controller.eventFilter(window, press) is True

        new_local = local + QPoint(60, 25)
        move = _mouse_event(
            QEvent.Type.MouseMove,
            new_local,
            window.mapToGlobal(new_local),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
        )
        assert controller.eventFilter(window, move) is True
        assert window.width() == start.width() + 60
        assert window.height() == start.height()  # 右边缘拖拽不改变高度

        release = _mouse_event(
            QEvent.Type.MouseButtonRelease,
            new_local,
            window.mapToGlobal(new_local),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
        )
        assert controller.eventFilter(window, release) is False
    finally:
        window.close()


def test_bottom_right_corner_drag_changes_both_dimensions(app):
    window = ChatUIWindow()
    window.show()
    app.processEvents()
    controller = window._resize_controller
    try:
        start = window.geometry()
        local = QPoint(start.width() - 1, start.height() - 1)
        press = _mouse_event(
            QEvent.Type.MouseButtonPress,
            local,
            window.mapToGlobal(local),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
        )
        assert controller.eventFilter(window, press) is True

        new_local = local + QPoint(-80, -60)
        move = _mouse_event(
            QEvent.Type.MouseMove,
            new_local,
            window.mapToGlobal(new_local),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
        )
        controller.eventFilter(window, move)
        assert window.width() == start.width() - 80
        assert window.height() == start.height() - 60
    finally:
        window.close()


def test_resize_respects_minimum_size(app):
    window = ChatUIWindow()
    window.show()
    app.processEvents()
    controller = window._resize_controller
    try:
        start = window.geometry()
        local = QPoint(start.width() - 2, start.height() // 2)
        press = _mouse_event(
            QEvent.Type.MouseButtonPress,
            local,
            window.mapToGlobal(local),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
        )
        controller.eventFilter(window, press)

        new_local = local + QPoint(-2000, 0)
        move = _mouse_event(
            QEvent.Type.MouseMove,
            new_local,
            window.mapToGlobal(new_local),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
        )
        controller.eventFilter(window, move)
        assert window.width() == window.minimumSize().width()
    finally:
        window.close()


def test_center_press_is_not_consumed_and_window_drag_still_works(app):
    window = ChatUIWindow()
    window.show()
    app.processEvents()
    controller = window._resize_controller
    try:
        local = QPoint(window.width() // 2, window.height() // 2)
        press = _mouse_event(
            QEvent.Type.MouseButtonPress,
            local,
            window.mapToGlobal(local),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
        )
        assert controller.eventFilter(window, press) is False
        # 中央按下应落入既有的拖拽移动逻辑
        window.mousePressEvent(press)
        assert window._drag_pos is not None
        assert window.width() == 820  # 尺寸不变
    finally:
        window.close()


# ── Ctrl + 滚轮缩放立绘 ────────────────────────────────────


def test_adjust_sprite_zoom_scales_and_clamps(app):
    window = ChatUIWindow()
    try:
        window._adjust_sprite_zoom(-5)
        assert window._user_sprite_zoom == pytest.approx(1.0 - 5 * 0.06)
        assert window.sprite_widget._scale == pytest.approx(window._user_sprite_zoom)

        window._adjust_sprite_zoom(-100)
        assert window._user_sprite_zoom == pytest.approx(0.2)
        assert window.sprite_widget._scale == pytest.approx(0.2)

        window._adjust_sprite_zoom(100)
        assert window._user_sprite_zoom == pytest.approx(1.0)
        assert window.sprite_widget._scale == pytest.approx(1.0)
    finally:
        window.close()


def test_user_zoom_multiplies_character_scale(app, tmp_path):
    sprite_path = tmp_path / "sprite.png"
    source = QPixmap(120, 240)
    source.fill()
    assert source.save(str(sprite_path))

    window = ChatUIWindow()
    try:
        window._user_sprite_zoom = 0.5
        assert window.set_sprite(str(sprite_path), 0.8) is None  # set_sprite 无返回值
        assert window._char_sprite_scale == pytest.approx(0.8)
        assert window.sprite_widget._scale == pytest.approx(0.4)
    finally:
        window.close()


def test_ctrl_wheel_event_zooms_sprite(app):
    window = ChatUIWindow()
    try:
        window._user_sprite_zoom = 0.5
        wheel_up = QWheelEvent(
            QPointF(100, 100),
            QPointF(100, 100),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ControlModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        window.wheelEvent(wheel_up)
        assert window._user_sprite_zoom == pytest.approx(0.5 + 0.06)

        # 无 Ctrl 的滚轮不改变缩放
        plain_wheel = QWheelEvent(
            QPointF(100, 100),
            QPointF(100, 100),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        window.wheelEvent(plain_wheel)
        assert window._user_sprite_zoom == pytest.approx(0.5 + 0.06)
    finally:
        window.close()
