"""Settings-only modal chrome and a parent-scoped dimming layer."""
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from ui.settings_ui.daylight import settings_qss
from ui.window_chrome import WindowDragController


class _Dimmer(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("settings_modal_dimmer")
        self.setStyleSheet("QWidget#settings_modal_dimmer { background: rgba(31, 42, 34, 72); }")
        self.setGeometry(parent.rect())
        parent.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize:
            self.setGeometry(watched.rect())
        return False


class _ModalSurface:
    def _setup_surface(self):
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setStyleSheet(settings_qss())
        parent = self.parentWidget()
        self._dimmer = _Dimmer(parent.window()) if parent else None
        if self._dimmer:
            self._dimmer.hide()
            self.destroyed.connect(self._dimmer.deleteLater)
        self.finished.connect(self._hide_dimmer)

    def _hide_dimmer(self, *_):
        if self._dimmer:
            self._dimmer.hide()

    def showEvent(self, event):
        if self._dimmer:
            self._dimmer.setGeometry(self._dimmer.parentWidget().rect())
            self._dimmer.show()
            self._dimmer.raise_()
        super().showEvent(event)
        if self.parentWidget():
            bounds = self.parentWidget().window().frameGeometry()
            self.move(bounds.center() - self.rect().center())

    def hideEvent(self, event):
        self._hide_dimmer()
        super().hideEvent(event)


class SettingsDialog(_ModalSurface, QDialog):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._setup_surface()
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(24, 20, 24, 20)
        self.body.setSpacing(18)
        titlebar = QWidget()
        row = QHBoxLayout(titlebar)
        row.setContentsMargins(0, 0, 0, 0)
        label = QLabel(title)
        label.setProperty("role", "card-title")
        close = QPushButton("×")
        close.setProperty("role", "chrome")
        close.setFixedSize(32, 32)
        close.setAccessibleName("Close dialog")
        close.clicked.connect(self.reject)
        row.addWidget(label, 1)
        row.addWidget(close)
        self.body.addWidget(titlebar)
        self._drag = WindowDragController(self, [titlebar, label])


class SettingsMessageBox(_ModalSurface, QMessageBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_surface()
        self.setMinimumWidth(440)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.layout().setContentsMargins(28, 24, 28, 24)
        self.layout().setSpacing(18)
        self.setStyleSheet(settings_qss() + '''
            QLabel#qt_msgbox_label { font-size: 23px; font-weight: 600; min-width: 360px; padding-bottom: 10px; }
            QLabel#qt_msgbox_informativelabel { font-size: 16px; min-width: 360px; padding-bottom: 18px; }
        ''')

    def showEvent(self, event):
        for button in self.buttons():
            role = self.buttonRole(button)
            if role in (QMessageBox.ButtonRole.YesRole, QMessageBox.ButtonRole.AcceptRole):
                button.setProperty("role", "primary")
            elif role == QMessageBox.ButtonRole.DestructiveRole:
                button.setProperty("role", "danger")
            button.style().unpolish(button)
            button.style().polish(button)
        super().showEvent(event)


def confirm(parent, title, description, *, detail="", thumbnail=None, action="确认", destructive=False):
    dialog = SettingsMessageBox(parent)
    dialog.setWindowTitle(title)
    dialog.setText(title)
    dialog.setInformativeText(description + ("\n\n" + detail if detail else ""))
    if thumbnail is not None and not thumbnail.isNull():
        dialog.setIconPixmap(thumbnail)
    cancel = dialog.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    accept = dialog.addButton(action, QMessageBox.ButtonRole.DestructiveRole if destructive else QMessageBox.ButtonRole.AcceptRole)
    dialog.setDefaultButton(cancel)
    dialog.exec()
    accepted = dialog.clickedButton() is accept
    dialog.deleteLater()
    return accepted
