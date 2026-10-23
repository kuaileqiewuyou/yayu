"""Reusable settings controls with safe wheel and popup behavior."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QIcon, QWheelEvent
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox


class _NoWheelMixin:
    """Prevent an accidental page scroll from editing the focused value."""

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()

    def setCurrentText(self, text: str) -> None:
        text_index = self.findText(text)
        data_index = self.findData(text, role=Qt.ItemDataRole.UserRole)
        target_index = text_index if text_index >= 0 else data_index
        if target_index >= 0:
            self.setCurrentIndex(target_index)
            return
        super().setCurrentText(text)


class NoWheelDoubleSpinBox(_NoWheelMixin, QDoubleSpinBox):
    pass


class NoWheelSpinBox(_NoWheelMixin, QSpinBox):
    pass


class SafeComboBox(QComboBox):
    """Combo box that ignores closed-state wheel edits and bounds its popup."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaxVisibleItems(10)
        self.view().setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.view().setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def addItem(self, *args) -> None:
        super().addItem(*args)
        text_index = 1 if args and isinstance(args[0], QIcon) else 0
        if len(args) > text_index:
            self.setItemData(self.count() - 1, str(args[text_index]), Qt.ItemDataRole.ToolTipRole)

    def addItems(self, texts) -> None:
        for item in texts:
            self.addItem(str(item))

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.view().isVisible():
            super().wheelEvent(event)
            return
        event.ignore()

    def showPopup(self) -> None:
        self._prepare_popup_width()
        super().showPopup()
        self._constrain_visible_popup()

    def _window_global_bounds(self):
        top_level = self.window()
        top_left = top_level.mapToGlobal(QPoint(0, 0))
        return top_level.rect().translated(top_left)

    def _preferred_popup_width(self) -> int:
        bounds = self._window_global_bounds()
        content_width = self.view().sizeHintForColumn(0) + 32
        return min(max(self.width(), content_width), max(1, bounds.width()))

    def _prepare_popup_width(self) -> None:
        width = self._preferred_popup_width()
        self.view().setMinimumWidth(width)
        self.view().setMaximumWidth(width)

    def _constrain_visible_popup(self) -> None:
        popup = self.view().window()
        bounds = self._window_global_bounds()
        width = min(self._preferred_popup_width(), bounds.width())
        height = min(popup.height(), max(1, bounds.height()))
        popup.resize(width, height)

        anchor = self.mapToGlobal(QPoint(0, self.height()))
        x = min(max(anchor.x(), bounds.left()), bounds.right() - width + 1)
        y = popup.y()
        if y < bounds.top():
            y = bounds.top()
        if y + height - 1 > bounds.bottom():
            above = self.mapToGlobal(QPoint(0, 0)).y() - height
            y = max(bounds.top(), above)
        popup.move(x, y)
