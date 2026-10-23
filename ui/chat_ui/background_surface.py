"""Cached cover image beneath the transparent character and dialogue layers."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget


class BackgroundSurface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = QPixmap()
        self._cover = QPixmap()
        self.background_path = ""
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_background(self, path, pixmap=None):
        source = pixmap if pixmap is not None else QPixmap(path) if path else QPixmap()
        if path and source.isNull():
            return False
        self._source = source
        self.background_path = path
        self._prepare_cover()
        self.update()
        return True

    def _prepare_cover(self):
        if self._source.isNull() or self.size().isEmpty():
            self._cover = QPixmap()
            return
        ratio = self.devicePixelRatioF()
        self._cover = self._source.scaled(
            self.size() * ratio, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._cover.setDevicePixelRatio(ratio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._prepare_cover()

    def paintEvent(self, event):
        if self._cover.isNull():
            return
        ratio = self._cover.devicePixelRatio()
        painter = QPainter(self)
        painter.drawPixmap(
            round((self.width() - self._cover.width() / ratio) / 2),
            round((self.height() - self._cover.height() / ratio) / 2), self._cover,
        )
        painter.end()
