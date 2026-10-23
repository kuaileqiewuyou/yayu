"""User-owned background selection, persisted without involving a model turn."""
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtGui import QImageReader, QPixmap

from config.background_assets import entries_from_background


def background_file(path: str) -> Path:
    file = Path(path)
    return file if file.is_absolute() else Path("data/backgrounds") / file


class ManualBackgroundController(QObject):
    def __init__(self, window, config, settings_window):
        super().__init__(window)
        self.window = window
        self.config = config
        self.settings_window = settings_window
        self._picker = None
        self.current_path = ""
        window.background_requested.connect(self.open_picker)
        settings_window.background_changed.connect(self.apply_saved_background)

    def restore(self):
        path = self.config.system_config.background_path
        pixmap = self._decode(path)
        if not path or not pixmap.isNull():
            self._display(path, pixmap)
        else:
            self._display("")
            self.window.set_reply_status("已保存的背景图片无法读取，请重新选择背景。", error=True)

    @staticmethod
    def _decode(path):
        if not path:
            return QPixmap()
        reader = QImageReader(str(background_file(path)))
        reader.setAutoTransform(True)
        return QPixmap.fromImage(reader.read())

    def _display(self, path, pixmap=None):
        self.window.set_background(str(background_file(path)) if path else "", pixmap=pixmap)
        self.current_path = path
        self.settings_window.set_current_background(path)

    def apply_saved_background(self, path):
        """Settings already completed its transaction before emitting this signal."""
        pixmap = self._decode(path)
        if path and pixmap.isNull():
            self.window.set_reply_status("背景图片无法读取，请重新选择背景。", error=True)
            return False
        self._display(path, pixmap)
        return True

    def select_background(self, path):
        pixmap = self._decode(path)
        if path and pixmap.isNull():
            self.window.set_reply_status("背景图片无法读取，请重新选择背景。", error=True)
            return False
        previous = self.config.system_config.background_path
        self.config.system_config.background_path = path
        try:
            self.config.save_system_config()
        except Exception as error:
            self.config.system_config.background_path = previous
            self.window.set_reply_status(f"背景保存失败：{error}", error=True)
            return False
        self._display(path, pixmap)
        return True

    def open_picker(self):
        if self._picker is not None:
            self._picker.raise_()
            self._picker.activateWindow()
            return
        # Decode library thumbnails only when the user asks to browse backgrounds.
        from ui.chat_ui.background_picker import BackgroundPicker
        backgrounds = self.config.backgrounds
        entries = entries_from_background(backgrounds[0]) if backgrounds else []
        picker = BackgroundPicker(entries, self.current_path, self.window)
        self._picker = picker
        picker.apply_requested.connect(lambda path: self._apply_from_picker(picker, path))
        picker.manage_requested.connect(self.settings_window.show_background_settings)
        picker.finished.connect(lambda _: self._picker_finished(picker))
        picker.open()

    def _apply_from_picker(self, picker, path):
        if self.select_background(path):
            picker.accept()
        else:
            picker.show_error("没有应用背景，请检查图片或保存位置后重试。")

    def _picker_finished(self, picker):
        if self._picker is picker:
            self._picker = None
