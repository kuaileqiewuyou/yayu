"""Small, settings-only layout primitives for the daylight theme."""
from __future__ import annotations

from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QGridLayout, QLayout, QScrollArea,
    QGroupBox, QSizePolicy, QBoxLayout, QHBoxLayout, QPushButton,
)


def heading(layout, title: str, description: str = ""):
    label = QLabel(title)
    label.setProperty("role", "heading")
    layout.addWidget(label)
    if description:
        hint = QLabel(description)
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
    return label


def scroll_content(content: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    content.setMinimumWidth(0)
    scroll.setWidget(content)
    return scroll


def page_layout(widget: QWidget, title: str, description: str = "") -> QVBoxLayout:
    outer = QVBoxLayout(widget)
    outer.setContentsMargins(0, 0, 0, 0)
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(28, 24, 28, 24)
    layout.setSpacing(20)
    heading(layout, title, description)
    outer.addWidget(scroll_content(content))
    return layout


def card(title: str):
    group = QGroupBox(title)
    layout = QVBoxLayout(group)
    layout.setSpacing(16)
    return group, layout


def hint(text, *, banner=False):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setProperty("role", "notice" if banner else "muted")
    return label


def row_widget(widgets, *, stretch=False):
    widget = QWidget()
    box = QHBoxLayout(widget)
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(12)
    for child in widgets:
        box.addWidget(child)
    if stretch:
        box.addStretch()
    return widget


def release_layout(layout):
    """Detach layout items so existing controls and their signals can be reused."""
    while layout.count():
        item = layout.takeAt(0)
        if item.layout():
            release_layout(item.layout())
        elif item.widget():
            item.widget().hide()


def decorate_actions(root):
    from ui.settings_ui.daylight import icon
    names = [("删除", "trash"), ("清除", "trash"), ("移除", "trash"),
             ("新增", "plus"), ("添加", "plus"), ("导入", "image"),
             ("导出", "upload"), ("保存", "save"), ("更新", "save"),
             ("刷新", "refresh"), ("重新检测", "refresh"), ("检查", "search"),
             ("校验", "check-circle"), ("预览", "search"), ("复制", "copy"),
             ("重命名", "edit"), ("打开", "folder"), ("选择", "folder"),
             ("整理", "memory"), ("重建", "tools"), ("填入", "file"),
             ("本轮", "file"), ("测试", "play")]
    for button in root.findChildren(QPushButton):
        if button.property("role") == "chrome" or not button.icon().isNull():
            continue
        for text, name in names:
            if text in button.text():
                button.setIcon(icon(name, light=button.property("role") == "primary"))
                button.setIconSize(QSize(20, 20))
                break


class ResponsiveFields(QWidget):
    """Label-over-input fields; two columns when there is space."""
    def __init__(self, fields, parent=None, *, breakpoint=650, columns=2, inline=False):
        super().__init__(parent)
        self.breakpoint = breakpoint
        self.wide_columns = columns
        self._columns = 0
        self.cells = []
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(14)
        for label, control in fields:
            cell = QWidget()
            cell.setMinimumWidth(0)
            cell.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            box = QHBoxLayout(cell) if inline else QVBoxLayout(cell)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(6)
            if label:
                caption = QLabel(label)
                if inline:
                    caption.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
                box.addWidget(caption)
            box.addWidget(control, 1 if inline else 0)
            self.cells.append(cell)
        self._reflow(1)

    def _reflow(self, columns):
        if self._columns == columns:
            return
        self._columns = columns
        while self.grid.count():
            self.grid.takeAt(0)
        for index, cell in enumerate(self.cells):
            self.grid.addWidget(cell, index // columns, index % columns)
        for column in range(self.wide_columns):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
        self.updateGeometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow(self.wide_columns if event.size().width() >= self.breakpoint else 1)


class ResponsiveColumns(QWidget):
    def __init__(self, widgets, *, breakpoint=900, stretches=None):
        super().__init__()
        self.breakpoint = breakpoint
        self.box = QBoxLayout(QBoxLayout.Direction.TopToBottom, self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(16)
        for index, widget in enumerate(widgets):
            widget.setMinimumWidth(0)
            self.box.addWidget(widget, stretches[index] if stretches else 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        direction = (QBoxLayout.Direction.LeftToRight if self.width() >= self.breakpoint
                     else QBoxLayout.Direction.TopToBottom)
        if self.box.direction() != direction:
            self.box.setDirection(direction)


class FlowLayout(QLayout):
    """Wrapping action/filter rows, including at the 800px window minimum."""
    def __init__(self, parent=None, spacing=8):
        super().__init__(parent)
        self.items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def __del__(self):
        # QLayout owns its layout items; release their Python wrappers before
        # Qt tears down the widgets, including during interpreter shutdown.
        while self.items:
            self.items.pop()

    def addItem(self, item):
        self.items.append(item)
        self.invalidate()

    def addStretch(self, *_):
        pass

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        return self.items[index] if 0 <= index < len(self.items) else None

    def takeAt(self, index):
        return self.items.pop(index) if 0 <= index < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), False)

    def minimumSize(self):
        size = QSize()
        for item in self.items:
            size = size.expandedTo(item.minimumSize())
        return size

    def sizeHint(self):
        return self.minimumSize()

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, True)

    def _arrange(self, rect, apply):
        x, y, height = rect.x(), rect.y(), 0
        for item in self.items:
            if item.isEmpty():
                continue
            size = item.sizeHint()
            size.setWidth(min(size.width(), rect.width()))
            if x > rect.x() and x + size.width() > rect.right() + 1:
                x, y, height = rect.x(), y + height + self.spacing(), 0
            if apply:
                item.setGeometry(QRect(x, y, size.width(), size.height()))
            x += size.width() + self.spacing()
            height = max(height, size.height())
        return y + height - rect.y()
