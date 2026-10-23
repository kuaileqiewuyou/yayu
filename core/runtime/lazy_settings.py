"""Keep hidden settings UI and image decoding outside the chat startup path."""
from typing import Callable
from PySide6.QtCore import QObject, Signal


class LazySettingsWindow(QObject):
    background_changed = Signal(str)
    always_on_top_changed = Signal(bool)
    character_selected = Signal(str)

    def __init__(self, factory: Callable):
        super().__init__()
        self._factory = factory
        self._window = None
        self._controller = None
        self._snapshot = None
        self._background_path = None
        self._owner_window = None
        self._active_character_id = None
        self._character_switch_enabled = True

    @property
    def is_created(self) -> bool:
        return self._window is not None

    @property
    def memory_tab(self):
        # Shutdown must not create a previously unopened settings window.
        return self._window.memory_tab if self._window is not None else None

    def set_mcp_runtime_controller(self, controller):
        self._controller = controller
        if self._window is not None:
            self._window.set_mcp_runtime_controller(controller)

    def refresh_mcp_status(self, snapshot):
        self._snapshot = snapshot
        if self._window is not None:
            self._window.refresh_mcp_status(snapshot)

    def show(self):
        if self._window is None:
            window = self._factory()
            set_managed = getattr(window, "set_character_switch_managed", None)
            if set_managed is not None:
                set_managed(True)
            set_active = getattr(window, "set_active_character_id", None)
            if set_active is not None and self._active_character_id is not None:
                set_active(self._active_character_id)
            set_enabled = getattr(window, "set_character_switch_enabled", None)
            if set_enabled is not None:
                set_enabled(self._character_switch_enabled)
            if self._controller is not None:
                window.set_mcp_runtime_controller(self._controller)
            if self._snapshot is not None:
                window.refresh_mcp_status(self._snapshot)
            if self._background_path is not None:
                window.set_current_background(self._background_path)
            changed = getattr(window, "background_changed", None)
            if changed is not None:
                changed.connect(self.background_changed.emit)
            top_changed = getattr(window, "always_on_top_changed", None)
            if top_changed is not None:
                top_changed.connect(self._on_always_on_top_changed)
            selected = getattr(window, "character_selected", None)
            if selected is not None:
                selected.connect(self.character_selected.emit)
            self._set_transient_owner(window)
            self._window = window
        self._window.show()

    def set_owner_window(self, window):
        self._owner_window = window
        if self._window is not None:
            self._set_transient_owner(self._window)

    def _set_transient_owner(self, settings):
        if self._owner_window is not None:
            self._sync_owner_stacking(settings)
            self._owner_window.winId()
            settings.winId()
            settings.windowHandle().setTransientParent(self._owner_window.windowHandle())

    def _sync_owner_stacking(self, settings):
        if self._owner_window is not None:
            from PySide6.QtCore import Qt
            from ui.window_behavior import apply_always_on_top
            enabled = bool(self._owner_window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
            apply_always_on_top(settings, enabled)

    def _on_always_on_top_changed(self, enabled):
        self.always_on_top_changed.emit(bool(enabled))
        if self._window is not None:
            # Keep open settings accessible above a pinned chat, including when
            # the preference is changed after both windows were already shown.
            self._set_transient_owner(self._window)

    def set_current_background(self, path):
        self._background_path = path
        if self._window is not None:
            self._window.set_current_background(path)

    def set_active_character_id(self, character_id: str):
        self._active_character_id = str(character_id or "")
        if self._window is not None:
            self._window.set_active_character_id(self._active_character_id)

    def set_character_switch_enabled(self, enabled: bool):
        self._character_switch_enabled = bool(enabled)
        if self._window is not None:
            self._window.set_character_switch_enabled(self._character_switch_enabled)

    def show_background_settings(self):
        self.show()
        self._window.settings_nav.setCurrentRow(2)
        self.raise_()
        self.activateWindow()

    def raise_(self):
        if self._window is not None:
            self._window.raise_()

    def activateWindow(self):
        if self._window is not None:
            self._window.activateWindow()

    def close(self):
        return self._window.close() if self._window is not None else True
