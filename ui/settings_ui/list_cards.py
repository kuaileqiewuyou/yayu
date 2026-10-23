"""Paint list cards without changing the underlying text/data used by saving."""
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QRect, QEvent
from PySide6.QtGui import QColor, QFont, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem, QStyleOptionButton

from ui.settings_ui.image_preview import image_preview


class CardListDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, *, formatter=None, height=102):
        super().__init__(parent)
        self.formatter = formatter
        self.height = height

    def sizeHint(self, option, index):
        return QSize(160, self.height)

    def editorEvent(self, event, model, option, index):
        if not (index.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            return super().editorEvent(event, model, option, index)
        toggle = (event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton)
        toggle = toggle or (event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Space)
        if toggle:
            state = index.data(Qt.ItemDataRole.CheckStateRole)
            return model.setData(index, Qt.CheckState.Unchecked.value if state == Qt.CheckState.Checked.value else Qt.CheckState.Checked.value,
                                 Qt.ItemDataRole.CheckStateRole)
        return False

    def paint(self, painter, option, index):
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        text = str(index.data() or "").replace("\u2028", "\n")
        if self.formatter:
            title, description = self.formatter(index)
        else:
            title, _, description = text.partition("\n")
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.setPen(QPen(QColor("#748976" if selected else "#DFE5DC"), 2 if selected else 1))
        painter.setBrush(QColor("#EFF4EC" if selected else "#FFFFFF"))
        painter.drawRoundedRect(option.rect.adjusted(2, 5, -2, -5), 6, 6)
        painter.setClipRect(option.rect.adjusted(4, 8, -4, -8))
        inset = 46 if index.data(Qt.ItemDataRole.CheckStateRole) is not None else 18
        if index.data(Qt.ItemDataRole.CheckStateRole) is not None:
            check = QStyleOptionButton()
            check.rect = QRect(option.rect.x() + 16, option.rect.y() + 18, 21, 21)
            check.state = QStyle.StateFlag.State_Enabled | (QStyle.StateFlag.State_On if index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked.value else QStyle.StateFlag.State_Off)
            styled.widget.style().drawPrimitive(QStyle.PrimitiveElement.PE_IndicatorCheckBox, check, painter, styled.widget)
        rect = option.rect.adjusted(inset, 16, -18, -12)
        font = QFont(option.font)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#263B32"))
        title_height = painter.fontMetrics().height() + 6
        painter.drawText(QRect(rect.x(), rect.y(), rect.width(), title_height), Qt.AlignmentFlag.AlignLeft,
                         painter.fontMetrics().elidedText(str(title), Qt.TextElideMode.ElideRight, rect.width()))
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor("#758078"))
        painter.drawText(rect.adjusted(0, title_height + 3, 0, 0), Qt.TextFlag.TextWordWrap, str(description))
        painter.restore()


class SceneGalleryDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, *, sprites=False):
        super().__init__(parent)
        self.sprites = sprites

    def sizeHint(self, option, index):
        return QSize(120, 280) if self.sprites else QSize(194, 158)

    def paint(self, painter, option, index):
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        styled.text = ""
        rect = option.rect.adjusted(10, 8, -10, -34)
        path = str(index.data(Qt.ItemDataRole.UserRole) if self.sprites else index.data() or "")
        pixmap = image_preview(path, rect.size())
        painter.save()
        painter.setPen(QPen(QColor("#748976" if option.state & QStyle.StateFlag.State_Selected else "#DFE5DC")))
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRoundedRect(option.rect.adjusted(3, 3, -3, -3), 6, 6)
        painter.fillRect(rect, QColor("#EEF2EA"))
        if not pixmap.isNull():
            painter.drawPixmap(rect.center().x() - pixmap.width() // 2, rect.center().y() - pixmap.height() // 2, pixmap)
        painter.setFont(option.font)
        painter.setPen(QColor("#33443B"))
        title = str(index.data()) if self.sprites else f"{index.row() + 1:02d}  {Path(path).name}"
        text = painter.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, rect.width())
        painter.drawText(QRect(rect.x(), rect.bottom() + 6, rect.width(), 26), Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()
