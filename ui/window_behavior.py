"""Window stacking changes shared by chat and its settings window."""
from PySide6.QtCore import Qt


def apply_always_on_top(window, enabled: bool) -> None:
    flag = Qt.WindowType.WindowStaysOnTopHint
    if bool(window.windowFlags() & flag) == bool(enabled):
        return
    visible = window.isVisible()
    geometry = window.saveGeometry()
    rectangle = window.geometry()
    state = window.windowState()
    no_activate = window.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
    try:
        # Qt hides windows when flags change. Keep their state and focus policy.
        window.setWindowFlag(flag, bool(enabled))
        window.restoreGeometry(geometry)
        if not state & (Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen):
            window.setGeometry(rectangle)
        window.setWindowState(state)
        if visible:
            window.show()
    finally:
        window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, no_activate)
