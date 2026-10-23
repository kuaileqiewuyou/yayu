"""Editable background rows keep each name beside its actual image file."""
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QSizePolicy, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from ui.settings_ui.image_preview import image_preview

_LABEL_ROLE = Qt.ItemDataRole.UserRole.value + 1


class _ResourceDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        # DisplayRole retains the file path for old callers; the row presents it.
        option.text = ""


class _Thumbnail(QLabel):
    def __init__(self, path, parent):
        super().__init__(parent)
        self._path = path
        self._loaded = False
        self.setFixedSize(84, 68)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def paintEvent(self, event):
        if not self._loaded:
            self._loaded = True
            source = Path(self._path)
            if not source.is_absolute():
                source = Path("data/backgrounds") / source
            preview = image_preview(str(source), self.size())
            if preview.isNull():
                self.setText("无预览")
            else:
                self.setPixmap(preview)
        super().paintEvent(event)


class _ResourceRow(QWidget):
    def __init__(self, owner, item, path, label):
        super().__init__()
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.owner = owner
        self.item = item
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(12)
        self.number = QLabel()
        self.number.setProperty("role", "muted")
        self.number.setFixedWidth(24)
        layout.addWidget(self.number, 0, Qt.AlignmentFlag.AlignTop)
        preview = _Thumbnail(path, self)
        layout.addWidget(preview, 0, Qt.AlignmentFlag.AlignTop)
        details = QVBoxLayout()
        details.setSpacing(5)
        caption = QLabel("背景名称")
        caption.setProperty("role", "muted")
        details.addWidget(caption)
        self.name_edit = QLineEdit(label)
        self.name_edit.setMinimumWidth(0)
        self.name_edit.setPlaceholderText("例如：书房")
        self.name_edit.textChanged.connect(self._set_label)
        self.name_edit.installEventFilter(self)
        details.addWidget(self.name_edit)
        self.filename = QLabel()
        self.filename.setProperty("role", "muted")
        self.filename.setMinimumWidth(0)
        self.filename.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.filename.setToolTip(path)
        self._filename = Path(path).name
        details.addWidget(self.filename)
        layout.addLayout(details, 1)

    def _set_label(self, text):
        self.item.setData(_LABEL_ROLE, text)
        if not self.owner._populating:
            self.owner.bindingsChanged.emit()

    def eventFilter(self, watched, event):
        if watched is self.name_edit and event.type() == QEvent.Type.FocusIn:
            self.owner.setCurrentItem(self.item)
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.filename.setText(self.filename.fontMetrics().elidedText(
            self._filename, Qt.TextElideMode.ElideMiddle, max(20, self.filename.width())))

    def set_number(self, index):
        self.number.setText(f"{index:02d}")
        self.name_edit.setObjectName(f"{self.owner.kind}_name_{index}")
        self.name_edit.setAccessibleName(f"Scene {index} name")


class ResourceListWidget(QListWidget):
    bindingsChanged = Signal()

    def __init__(self, kind="scene", parent=None):
        super().__init__(parent)
        self.kind = kind
        self._populating = False
        self.setMinimumWidth(0)
        self.setSpacing(4)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setItemDelegate(_ResourceDelegate(self))
        self.setStyleSheet("""
            QListWidget { border: none; padding: 0; }
            QListWidget::item { padding: 0; margin: 0; }
        """)
        self._empty = QLabel(self.viewport())
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)
        self._empty.setProperty("role", "muted")
        self._empty.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._empty.setText("还没有背景图\n点击“添加图片”，再填写背景名称。")
        self.model().rowsRemoved.connect(self._refresh_rows)
        self._refresh_rows()

    def addItem(self, item):
        if isinstance(item, str):
            item = QListWidgetItem(item)
        label = item.data(_LABEL_ROLE)
        if label is None:
            label = Path(item.text()).stem
            item.setData(_LABEL_ROLE, label)
        super().addItem(item)
        row = _ResourceRow(self, item, item.text(), label)
        item.setSizeHint(QSize(160, 142))
        self.setItemWidget(item, row)
        if not self._populating:
            self._refresh_rows()
            self.bindingsChanged.emit()

    def takeItem(self, row):
        item = self.item(row)
        widget = self.itemWidget(item) if item is not None else None
        if widget is not None:
            widget.hide()
        result = super().takeItem(row)
        self._refresh_rows()
        self.bindingsChanged.emit()
        return result

    def clear(self):
        for index in range(self.count()):
            row = self.itemWidget(self.item(index))
            if row is not None:
                row.hide()
        super().clear()
        if not self._populating:
            self._refresh_rows()
            self.bindingsChanged.emit()

    def named_entries(self):
        entries = []
        for index in range(self.count()):
            item = self.item(index)
            label = str(item.data(_LABEL_ROLE) or "").strip() or Path(item.text()).stem
            entries.append({"path": item.text(), "label": label})
        return entries

    def set_named_entries(self, entries):
        self._populating = True
        self.setUpdatesEnabled(False)
        try:
            self.clear()
            for entry in entries:
                item = QListWidgetItem(entry["path"])
                item.setData(_LABEL_ROLE, entry["label"])
                self.addItem(item)
        finally:
            self._populating = False
            self.setUpdatesEnabled(True)
            self._refresh_rows()
        self.bindingsChanged.emit()

    def _refresh_rows(self, *_):
        self.setFixedHeight(min(420, max(190, self.count() * 150 + 12)))
        for index in range(self.count()):
            row = self.itemWidget(self.item(index))
            if row is not None:
                row.set_number(index + 1)
        self._empty.setGeometry(self.viewport().rect().adjusted(12, 12, -12, -12))
        self._empty.setVisible(self.count() == 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_rows()
        self.doItemsLayout()
