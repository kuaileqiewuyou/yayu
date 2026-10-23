import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from ui.chat_ui.background_surface import BackgroundSurface


def test_cover_crops_image_without_tiling_and_none_restores_transparency(tmp_path):
    app = QApplication.instance() or QApplication([])
    image = QImage(100, 50, QImage.Format.Format_RGB32)
    for x in range(100):
        color = QColor("red" if x < 25 else "blue" if x >= 75 else "green")
        for y in range(50):
            image.setPixelColor(x, y, color)
    path = tmp_path / "wide.png"
    image.save(str(path))
    surface = BackgroundSurface()
    surface.resize(100, 100)
    surface.show()
    try:
        app.processEvents()
        assert surface.set_background(str(path))
        pixels = surface.grab().toImage()
        ratio = pixels.width() / 100
        for x, y in ((10, 10), (90, 10), (10, 90), (90, 90)):
            assert pixels.pixelColor(round(x * ratio), round(y * ratio)).name() == "#008000"
        assert not surface.set_background(str(tmp_path / "missing.png"))
        assert surface.background_path == str(path)
        assert surface.set_background("")
        assert surface.grab().toImage().pixelColor(50, 50).alpha() == 0
    finally:
        surface.close()
        surface.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
