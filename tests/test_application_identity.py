"""The Python-hosted windows use the same artwork as both Windows launchers."""
from types import SimpleNamespace

import pytest

from core.runtime import application_identity


def test_non_windows_shell_identity_is_a_no_op(monkeypatch):
    monkeypatch.setattr(application_identity.sys, "platform", "linux")
    assert application_identity.prepare_application_identity("Yayu.Chat") is False


@pytest.mark.parametrize("result, expected", [(0, True), (-1, False)])
def test_windows_shell_receives_the_explicit_product_identity(monkeypatch, result, expected):
    received = []

    def set_app_id(value):
        received.append(value)
        return result

    monkeypatch.setattr(application_identity.sys, "platform", "win32")
    monkeypatch.setattr(application_identity.ctypes, "windll", SimpleNamespace(
        shell32=SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=set_app_id),
    ), raising=False)

    assert application_identity.prepare_application_identity("Yayu.Chat") is expected
    assert received == ["Yayu.Chat"]
    assert set_app_id.argtypes == [application_identity.ctypes.c_wchar_p]
    assert set_app_id.restype is application_identity.ctypes.c_long


def test_shell_identity_failure_keeps_the_application_launchable(monkeypatch):
    def unavailable(_value):
        raise OSError("desktop shell unavailable")

    monkeypatch.setattr(application_identity.sys, "platform", "win32")
    monkeypatch.setattr(application_identity.ctypes, "windll", SimpleNamespace(
        shell32=SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=unavailable),
    ), raising=False)
    assert application_identity.prepare_application_identity("Yayu.Settings") is False


def test_qt_default_uses_the_shared_application_icon(monkeypatch):
    from ui import resources

    received = []
    token = object()
    monkeypatch.setattr(resources, "application_icon", lambda: token)
    application_identity.apply_application_icon(SimpleNamespace(
        setApplicationName=lambda name: received.append(("name", name)),
        setApplicationDisplayName=lambda name: received.append(("display_name", name)),
        setWindowIcon=received.append,
    ))
    assert received == [("name", "Yayu"), ("display_name", "芽语"), token]


def test_launcher_artwork_is_available_at_small_and_large_qt_sizes(qapp):
    from ui.resources import application_icon

    icon = application_icon()
    assert not icon.isNull()
    assert {size.width() for size in icon.availableSizes()} >= {16, 32, 48, 256}
    assert not icon.pixmap(24, 24).isNull()


def test_chat_window_uses_the_shared_application_icon(qapp):
    from ui.chat_ui.chat_ui import ChatUIWindow
    from ui.resources import application_icon

    window = ChatUIWindow()
    try:
        assert window.windowTitle() == "芽语"
        assert window.accessibleName() == "Yayu main window"
        assert window.windowIcon().pixmap(32, 32).toImage() == application_icon().pixmap(32, 32).toImage()
    finally:
        window.close()
        window.deleteLater()
