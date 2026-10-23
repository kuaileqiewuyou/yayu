"""Short snapshot transition; real pages retain their layout, focus and scroll state."""
from PySide6.QtCore import QElapsedTimer, QEvent, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from ui import motion


class PageTransition(QWidget):
    def __init__(self, tabs):
        super().__init__(tabs)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._snapshot = QPixmap()
        self._direction = 1
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._on_frame)
        tabs.installEventFilter(self)
        self.hide()

    def start(self, page, direction=1, *, enabled=True):
        self.finish()
        if not enabled or motion.reduced_motion() or not page.isVisible():
            return
        page.ensurePolished()
        if page.layout():
            page.layout().activate()
        self._snapshot = page.grab()
        if self._snapshot.isNull():
            return
        self._direction = direction
        self.setGeometry(QRect(page.mapTo(self.parentWidget(), QPoint()), page.size()))
        self._clock.start()
        self.show()
        self.raise_()
        self._timer.start()
        self.update()

    def progress(self):
        return min(1.0, self._clock.elapsed() / motion.PAGE) if self._clock.isValid() else 1.0

    def finish(self):
        self._timer.stop()
        self.hide()
        self._snapshot = QPixmap()

    def refresh_motion_preferences(self):
        if motion.reduced_motion():
            self.finish()

    def _on_frame(self):
        if motion.reduced_motion() or self.progress() >= 1.0:
            self.finish()
        else:
            self.update()

    def paintEvent(self, event):
        eased = 1 - (1 - self.progress()) ** 3
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#FAFBF8"))
        painter.setOpacity(eased)
        offset = round((1 - eased) * motion.PAGE_SLIDE_PX * self._direction)
        painter.drawPixmap(offset, 0, self._snapshot)
        painter.end()

    def eventFilter(self, watched, event):
        if hasattr(self, "_timer") and event.type() in (QEvent.Type.Resize, QEvent.Type.Hide, QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress):
            self.finish()
        return super().eventFilter(watched, event)
