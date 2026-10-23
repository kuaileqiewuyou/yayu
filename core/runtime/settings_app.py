"""Settings application bootstrap and lifecycle coordinator."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Sequence

from PySide6.QtWidgets import QApplication

from config.config_manager import ConfigManager
from core.runtime.application_identity import SETTINGS_APP_ID, apply_application_icon, prepare_application_identity
from i18n import init_i18n
from ui.settings_ui.window import SettingsWindow
from ui.theme import dialogs_qss


@dataclass
class SettingsAppHandles:
    """Objects that must stay alive for the settings app event loop."""

    app: QApplication
    config: ConfigManager
    window: SettingsWindow


def build_settings_app(argv: Sequence[str] | None = None) -> SettingsAppHandles:
    """Build the settings application graph without entering the Qt event loop."""
    prepare_application_identity(SETTINGS_APP_ID)
    app = QApplication(list(sys.argv if argv is None else argv))
    apply_application_icon(app)
    app.setStyleSheet(dialogs_qss())
    config = ConfigManager()
    init_i18n(config.system_config.ui_language)
    window = SettingsWindow()
    return SettingsAppHandles(app=app, config=config, window=window)


def run_settings_app(argv: Sequence[str] | None = None) -> int:
    """Build and run the settings application."""
    handles = build_settings_app(argv)
    handles.window.show()
    from core.runtime.update_lifecycle import schedule_update_healthcheck
    schedule_update_healthcheck()
    return handles.app.exec()
