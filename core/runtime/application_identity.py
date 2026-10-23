"""Desktop shell identity without importing Qt during bootstrap module loading."""
from __future__ import annotations

import ctypes
import sys


APPLICATION_NAME = "Yayu"
APPLICATION_DISPLAY_NAME = "芽语"
APPLICATION_TAGLINE = "有角色、有故事的 AI 桌面伙伴"
CHAT_APP_ID = "Yayu.Chat"
SETTINGS_APP_ID = "Yayu.Settings"


def prepare_application_identity(app_id: str) -> bool:
    """Identify the Python process before Qt creates any native windows."""
    if sys.platform != "win32":
        return False
    try:
        set_app_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        set_app_id.argtypes = [ctypes.c_wchar_p]
        set_app_id.restype = ctypes.c_long
        return set_app_id(app_id) >= 0
    except (AttributeError, OSError):
        return False


def apply_application_icon(app) -> None:
    """Set the product name and icon inherited by dialogs and secondary windows."""
    from ui.resources import application_icon

    app.setApplicationName(APPLICATION_NAME)
    app.setApplicationDisplayName(APPLICATION_DISPLAY_NAME)
    app.setWindowIcon(application_icon())
