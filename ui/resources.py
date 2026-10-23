"""Application-local fonts and scalable chrome icons; no system installation."""
from pathlib import Path

from PySide6 import QtSvg  # noqa: F401 - register Qt's SVG icon backend on Windows
from PySide6.QtCore import QSize
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

ASSETS = Path(__file__).parent / "assets"
FONT_FAMILY = "ChillRoundF"
FONT_STACK = '"ChillRoundF", "Noto Sans SC", "Microsoft YaHei UI", "Segoe UI", sans-serif'


def application_icon() -> QIcon:
    """Use the launchers' multi-size artwork for every application surface."""
    # Older source checkouts and saved character avatars still use the old paths.
    for filename in ("yayu.ico", "yayu.png", "galgame-agent.ico", "galgame-agent.png"):
        result = QIcon(str(ASSETS / filename))
        if not result.isNull():
            return result
    return QIcon()


def ensure_ui_font() -> None:
    app = QApplication.instance()
    if app is None or app.property("galgame_font_loaded"):
        return
    font_id = QFontDatabase.addApplicationFont(str(ASSETS / "fonts" / "ChillRoundF.ttf"))
    if font_id < 0:
        return  # Keep the platform fallback when resources are unavailable.
    families = QFontDatabase.applicationFontFamilies(font_id)
    if families:
        font = QFont(app.font())
        font.setFamily(families[0])
        app.setFont(font)
        app.setProperty("galgame_font_loaded", True)


def chrome_icon(name: str, size: int = 20, *, light: bool = False) -> QIcon:
    suffix = "-light" if light else ""
    result = QIcon(str(ASSETS / "icons" / f"{name}{suffix}.svg"))
    result.addFile(str(ASSETS / "icons" / f"{name}{suffix}.svg"), QSize(size, size))
    return result


def set_button_icon(button, name: str, size: int = 20, *, light: bool = False) -> None:
    button.setText("")
    button.setIcon(chrome_icon(name, size, light=light))
    button.setIconSize(QSize(size, size))
    button.setProperty("icon_name", name)
