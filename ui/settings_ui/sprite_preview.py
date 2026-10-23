"""On-demand full-size sprite viewer; thumbnails stay cheap in the editor."""
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QImageReader, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)
from ui.settings_ui.dialogs import SettingsDialog


class SpriteImageView(QGraphicsView):
    zoom_changed = Signal(float)

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        scene = QGraphicsScene(self)
        item = scene.addPixmap(pixmap)
        item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        scene.setSceneRect(item.boundingRect())
        self.setScene(scene)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setBackgroundBrush(QColor("#E9EDE3"))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.fit_mode = True

    def fit_image(self):
        self.fit_mode = True
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.zoom_changed.emit(self.transform().m11())

    def drawBackground(self, painter, rect):
        # Draw in viewport pixels so checks stay the same size while zooming.
        painter.save()
        painter.resetTransform()
        bounds = self.viewport().rect()
        painter.fillRect(bounds, QColor("#FAFBF8"))
        tile = 18
        for y in range(0, bounds.height(), tile):
            for x in range(0, bounds.width(), tile):
                if (x // tile + y // tile) % 2:
                    painter.fillRect(x, y, tile, tile, QColor("#E8EDE5"))
        painter.restore()

    def original_size(self):
        self.fit_mode = False
        self.resetTransform()
        self.zoom_changed.emit(1.0)

    def zoom(self, factor: float):
        self.fit_mode = False
        current = self.transform().m11()
        target = min(8.0, max(0.02, current * factor))
        self.scale(target / current, target / current)
        self.zoom_changed.emit(target)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta:
            self.zoom(1.2 if delta > 0 else 1 / 1.2)
            event.accept()
        else:
            super().wheelEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fit_mode:
            self.fit_image()


class SpritePreviewDialog(SettingsDialog):
    def __init__(self, image_path: str, parent=None):
        super().__init__("立绘预览", parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setObjectName("sprite_preview_dialog")
        self.setWindowTitle(f"立绘预览 · {Path(image_path).name}")
        reader = QImageReader(image_path)
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            self.deleteLater()
            raise ValueError("无法预览这张立绘，请检查文件是否存在或是否为有效图片。")
        self.resize(700, 820)
        available = self.screen().availableGeometry()
        self.resize(min(self.width(), available.width()), min(self.height(), available.height()))
        layout = self.body
        info = QLabel(f"{Path(image_path).name}  ·  {image.width()} × {image.height()}")
        info.setToolTip(image_path)
        info.setWordWrap(True)
        layout.addWidget(info)
        self.view = SpriteImageView(QPixmap.fromImage(image), self)
        layout.addWidget(self.view, 1)
        actions = QHBoxLayout()
        for text, name, callback in [
            ("−", "sprite_zoom_out", lambda: self.view.zoom(1 / 1.25)),
            ("＋", "sprite_zoom_in", lambda: self.view.zoom(1.25)),
            ("适应窗口", "sprite_fit", self.view.fit_image),
            ("原始大小", "sprite_original", self.view.original_size),
        ]:
            button = QPushButton(text)
            button.setObjectName(name)
            button.clicked.connect(callback)
            actions.addWidget(button)
        self.zoom_label = QLabel()
        self.view.zoom_changed.connect(lambda zoom: self.zoom_label.setText(f"{zoom:.0%}"))
        actions.addWidget(self.zoom_label)
        actions.addStretch()
        actions.addWidget(QLabel("滚轮缩放 · 按住图片拖动"))
        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        actions.addWidget(close)
        layout.addLayout(actions)

    def showEvent(self, event):
        super().showEvent(event)
        self.view.fit_image()
