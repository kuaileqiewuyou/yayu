"""Shared behavior for project-drawn frameless title bars."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt


class WindowDragController(QObject):
    def __init__(self, window, surfaces, *, toggle_maximize: bool = False):
        super().__init__(window)
        self.window = window
        self.toggle_maximize = toggle_maximize
        self._drag_offset = None
        for surface in surfaces:
            surface.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonDblClick:
            if self.toggle_maximize and event.button() == Qt.MouseButton.LeftButton:
                self._toggle_maximized()
                event.accept()
                return True

        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_offset = event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()
                handle = self.window.windowHandle()
                if handle is not None and not self.window.isMaximized() and handle.startSystemMove():
                    self._drag_offset = None
                event.accept()
                return True

        if event.type() == QEvent.Type.MouseMove:
            if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
                self.window.move(event.globalPosition().toPoint() - self._drag_offset)
                event.accept()
                return True

        if event.type() == QEvent.Type.MouseButtonRelease:
            self._drag_offset = None

        return super().eventFilter(watched, event)

    def _toggle_maximized(self) -> None:
        if self.window.isMaximized():
            self.window.showNormal()
        else:
            self.window.showMaximized()


class FramelessResizeController(QObject):
    """无边框窗口的 8 向边缘拖拽缩放。

    手动实现（而非 startSystemResize），保证离屏/测试环境行为一致。
    与窗口拖拽移动共存：仅当按下点落在窗口边缘 margin 内时才接管事件，
    其余区域事件照常传递给窗口的拖拽移动逻辑。
    """

    def __init__(self, window, *, margin: int = 6):
        super().__init__(window)
        self._window = window
        self._margin = margin
        self._edges = Qt.Edges(0)
        self._press_global: QPoint | None = None
        self._press_geometry: QRect | None = None
        window.installEventFilter(self)
        window.setMouseTracking(True)

    # ── 命中测试与光标 ─────────────────────────────────────
    @staticmethod
    def edges_at(rect: QRect, pos: QPoint, margin: int) -> Qt.Edges:
        """判断 pos 命中了窗口 rect 的哪些边缘。"""
        edges = Qt.Edges(0)
        if pos.x() <= margin:
            edges |= Qt.Edge.LeftEdge
        elif pos.x() >= rect.width() - 1 - margin:
            edges |= Qt.Edge.RightEdge
        if pos.y() <= margin:
            edges |= Qt.Edge.TopEdge
        elif pos.y() >= rect.height() - 1 - margin:
            edges |= Qt.Edge.BottomEdge
        return edges

    @staticmethod
    def cursor_for_edges(edges: Qt.Edges) -> Qt.CursorShape | None:
        horizontal = bool(edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge))
        vertical = bool(edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge))
        if horizontal and vertical:
            if (edges & Qt.Edge.LeftEdge and edges & Qt.Edge.TopEdge) or (
                edges & Qt.Edge.RightEdge and edges & Qt.Edge.BottomEdge
            ):
                return Qt.CursorShape.SizeFDiagCursor
            return Qt.CursorShape.SizeBDiagCursor
        if horizontal:
            return Qt.CursorShape.SizeHorCursor
        if vertical:
            return Qt.CursorShape.SizeVerCursor
        return None

    # ── 事件处理 ──────────────────────────────────────────
    def eventFilter(self, watched, event):
        # 防御性取属性：窗口销毁后、Python 包装对象被 GC 半拆解时，
        # Qt 仍可能向本过滤器投递事件，此时直接忽略。
        window = getattr(self, "_window", None)
        if window is None or watched is not window:
            return False
        etype = event.type()

        if etype == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            edges = self.edges_at(self._window.rect(), event.position().toPoint(), self._margin)
            if edges and not self._window.isMaximized():
                self._edges = edges
                self._press_global = event.globalPosition().toPoint()
                self._press_geometry = self._window.geometry()
                event.accept()
                return True
            return False

        if etype == QEvent.Type.MouseMove:
            if self._press_global is not None and event.buttons() & Qt.MouseButton.LeftButton:
                self._perform_resize(event.globalPosition().toPoint())
                event.accept()
                return True
            self._update_hover_cursor(event.position().toPoint())
            return False

        if etype == QEvent.Type.MouseButtonRelease:
            self._edges = Qt.Edges(0)
            self._press_global = None
            self._press_geometry = None
            return False

        if etype == QEvent.Type.Leave:
            self._window.unsetCursor()
            return False

        return False

    # ── 内部实现 ──────────────────────────────────────────
    def _perform_resize(self, global_pos: QPoint) -> None:
        delta = global_pos - self._press_global
        geometry = QRect(self._press_geometry)
        minimum = self._window.minimumSize()
        min_width = max(1, minimum.width())
        min_height = max(1, minimum.height())
        edges = self._edges

        if edges & Qt.Edge.LeftEdge:
            geometry.setLeft(min(geometry.right() - min_width + 1, geometry.left() + delta.x()))
        elif edges & Qt.Edge.RightEdge:
            geometry.setRight(max(geometry.left() + min_width - 1, geometry.right() + delta.x()))
        if edges & Qt.Edge.TopEdge:
            geometry.setTop(min(geometry.bottom() - min_height + 1, geometry.top() + delta.y()))
        elif edges & Qt.Edge.BottomEdge:
            geometry.setBottom(max(geometry.top() + min_height - 1, geometry.bottom() + delta.y()))

        self._window.setGeometry(geometry)

    def _update_hover_cursor(self, pos: QPoint) -> None:
        if self._press_global is not None:
            return
        shape = self.cursor_for_edges(self.edges_at(self._window.rect(), pos, self._margin))
        if shape is None:
            self._window.unsetCursor()
        else:
            self._window.setCursor(shape)
