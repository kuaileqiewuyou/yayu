"""Settings palette. Deliberately independent of the chat window theme."""
from pathlib import Path

# Load the SVG backend before Qt's icon/image plugins resolve SVG resources on Windows.
from PySide6 import QtSvg  # noqa: F401
from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from ui.resources import FONT_STACK

COLOR_DIM = "#657169"
COLOR_OK = "#526F58"
COLOR_WARN = "#936623"
COLOR_ERR = "#AD514A"


def icon(name, size=22, *, light=False):
    # Keep rendering and ownership in Qt's SVG icon engine. Temporary Python
    # QSvgRenderer/QPainter objects can crash during mixed-window GC on Qt 6.8.
    assets = Path(__file__).parent / "assets"
    result = QIcon(str(assets / f"{name}{'-selected' if light else ''}.svg"))
    result.addFile(str(assets / f"{name}-selected.svg"), QSize(size, size), QIcon.Mode.Selected)
    return result


def settings_qss():
    assets = (Path(__file__).parent / "assets").as_posix()
    return """
    QWidget { background: transparent; color: #233039; font-family: FONT_STACK; font-size: 16px; }
    QMainWindow#settings_window, QDialog, QMessageBox { background: #FAFBF8; }
    QLabel, QCheckBox, QTabBar, QSplitter { background: transparent; }
    QLabel[role="heading"] { font-family: "Noto Serif SC", "Source Han Serif SC", "SimSun"; font-size: 34px; font-weight: 700; color: #233039; }
    QLabel[role="muted"] { color: #758078; }
    QLabel[role="notice"] { background: #EFF3ED; color: #657169; padding: 14px 18px; border-radius: 7px; }
    QLabel[role="card-title"] { font-size: 22px; font-weight: 600; }
    QLabel[role="character-name"] { font-family: "SimSun"; font-size: 24px; font-weight: 700; }
    QWidget#settings_titlebar { background: #FCFCFA; border-bottom: 1px solid #DCE2D9; }
    QLabel#settings_title_label { font-size: 18px; font-weight: 500; }
    QWidget#settings_bottom_bar { background: #FCFCFA; border-top: 1px solid #DCE2D9; }
    QWidget#memory_editor_card { background: #FFFFFF; border: 1px solid #DAE1D7; border-radius: 8px; }
    QListWidget#settings_nav { background: #F3F5F0; border: none; border-right: 1px solid #DCE2D9; border-radius: 0; padding: 18px 10px; font-size: 18px; }
    QListWidget#settings_nav::item { padding: 12px 12px; margin: 5px 0; border: none; border-radius: 8px; }
    QListWidget#settings_nav::item:selected { background: #748976; color: white; }
    QListWidget#settings_nav::item:hover:!selected { background: #E3E9DF; }
    QGroupBox { background: #FFFFFF; border: 1px solid #DAE1D7; border-radius: 8px; margin-top: 0; padding: 58px 18px 18px; font-size: 22px; font-weight: 600; }
    QGroupBox::title { subcontrol-origin: padding; subcontrol-position: top left; top: 18px; left: 18px; padding: 0; background: transparent; }
    QPushButton { background: #FFFFFF; border: 1px solid #D4DDD2; border-radius: 7px; padding: 10px 16px; color: #33443B; }
    QPushButton:hover { background: #EDF2E9; border-color: #93A68F; }
    QPushButton:pressed { background: #DFE7DA; }
    QPushButton:disabled { background: #F0F2ED; border-color: #E3E7DF; color: #9AA399; }
    QPushButton[role="primary"] { background: #748976; border-color: #748976; color: white; font-weight: 600; }
    QPushButton[role="primary"]:hover { background: #607B65; }
    QPushButton[role="danger"] { color: #AD514A; background: #FFFAF8; border-color: #E3C6BE; }
    QPushButton[role="primary"]:disabled, QPushButton[role="danger"]:disabled { background: #F0F2ED; border-color: #E3E7DF; color: #9AA399; }
    QPushButton[role="chrome"] { border: none; background: transparent; padding: 0; font-size: 16px; }
    QPushButton[role="chrome"]:hover { background: #E8EDE3; }
    QPushButton#settings_close_button:hover { background: #F3DEDA; color: #AD514A; }
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #FFFFFF; color: #233039; border: 1px solid #D5DDD2; border-radius: 6px; padding: 9px 12px; selection-background-color: #DCE7D7; selection-color: #233039; }
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 1px solid #748976; }
    QLineEdit:read-only, QPlainTextEdit:read-only { background: #F3F5EF; }
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled { background: #F0F2ED; color: #8E998E; }
    QComboBox { padding-right: 26px; }
    QComboBox::drop-down { border: none; width: 25px; }
    QComboBox::down-arrow { image: url(ASSETS/down.svg); width: 12px; height: 12px; }
    QComboBox QAbstractItemView { background: #FFFFFF; color: #233039; selection-background-color: #E2EBDD; selection-color: #233039; border: 1px solid #CBD6C6; }
    QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 22px; border-left: 1px solid #D5DDD2; }
    QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 22px; border-left: 1px solid #D5DDD2; }
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url(ASSETS/up.svg); width: 10px; height: 10px; }
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url(ASSETS/down.svg); width: 10px; height: 10px; }
    QCheckBox { spacing: 8px; }
    QCheckBox::indicator, QListView::indicator { width: 21px; height: 21px; background: white; border: 1px solid #9AA995; border-radius: 4px; }
    QCheckBox::indicator:checked, QListView::indicator:checked { background: #748976; border-color: #748976; image: url(ASSETS/check.svg); }
    QScrollArea { background: transparent; border: none; }
    QListWidget, QTableWidget { background: #FFFFFF; alternate-background-color: #F6F8F2; border: 1px solid #DAE1D7; border-radius: 8px; padding: 4px; outline: none; gridline-color: #E1E6DD; }
    QListWidget::item { padding: 10px 8px; margin: 2px 0; border: 1px solid transparent; border-radius: 6px; }
    QListWidget::item:selected { background: #E7EEE1; color: #233D2A; border-color: #98AC93; }
    QListWidget::item:hover:!selected { background: #F2F5EC; }
    QTableWidget::item { padding: 5px; }
    QTableWidget::item:selected { background: #E7EEE1; color: #233D2A; }
    QHeaderView::section { background: #EFF3E9; color: #465B49; padding: 8px; border: none; border-bottom: 1px solid #D5DDD2; }
    QTabWidget::pane { border: none; }
    QTabBar::tab { background: transparent; color: #657169; padding: 14px 18px; font-size: 18px; border-bottom: 2px solid transparent; }
    QTabBar::tab:selected { color: #48604C; border-bottom-color: #748976; font-weight: 600; }
    QTabBar::tab:hover { background: #E9EFE3; }
    QSplitter::handle { background: #DAE1D7; }
    QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
    QScrollBar:horizontal { background: transparent; height: 8px; margin: 0; }
    QScrollBar::handle { background: #BECBB8; border-radius: 4px; min-height: 24px; min-width: 24px; }
    QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
    QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
    QGroupBox[role="plain"], QFrame[role="plain"] { border: none; background: transparent; padding: 0; margin: 0; }
    QListWidget[role="cards"] { border: none; background: transparent; padding: 0; }
    QListWidget[role="cards"]::item { border: 1px solid #DFE5DC; background: white; padding: 18px 14px; margin: 5px 0; }
    QListWidget[role="cards"]::item:selected { border: 2px solid #748976; background: #EFF4EC; }
    QLabel[role="badge"] { background: #E7EFE1; color: #48604C; padding: 5px 10px; border-radius: 12px; }
    QLabel[state="failed"] { background: #FFF2EF; color: #AD514A; border: 1px solid #E9C5BE; border-radius: 7px; padding: 14px; }
    QLabel[state="running"], QLabel[state="queued"] { background: #EDF4EB; color: #526F58; border: 1px solid #A4B7A0; border-radius: 7px; padding: 14px; }
    QWidget#settings_window[compact="true"] QWidget { font-size: 13px; }
    QWidget#settings_window[compact="true"] QLabel[role="heading"] { font-size: 25px; }
    QWidget#settings_window[compact="true"] QGroupBox { font-size: 18px; padding: 48px 12px 12px; }
    QWidget#settings_window[compact="true"] QGroupBox[role="plain"] { padding: 0; }
    QWidget#settings_window[compact="true"] QPushButton { padding: 7px 10px; }
    QWidget#settings_window[compact="true"] QTabBar::tab { padding: 10px 12px; font-size: 14px; }
    QWidget#settings_window[compact="true"] QListWidget#settings_nav { font-size: 13px; padding: 12px 7px; }
    QWidget#settings_window[compact="true"] QListWidget#settings_nav::item { padding: 10px 6px; margin: 3px 0; }
    QToolTip { background: #FFFFFF; color: #233039; border: 1px solid #CBD6C6; padding: 6px; }
    """.replace("ASSETS", assets).replace("FONT_STACK", FONT_STACK)
