import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QFrame, QPushButton

from core.runtime import chat_actions
from ui.chat_ui.chat_ui import ChatUIWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_session_skills_dialog_uses_project_drawn_frameless_chrome(app, monkeypatch):
    session = SimpleNamespace(id="session-1", title="雨夜咖啡馆", enabled_skills=["memory"])
    history = SimpleNamespace(
        get_session_store=lambda: SimpleNamespace(get_session=lambda session_id: session),
    )
    config = SimpleNamespace(skills_root="ignored")
    repository = SimpleNamespace(
        list_skills=lambda: [SimpleNamespace(name="memory", description="维护角色记忆")]
    )
    monkeypatch.setattr(chat_actions, "SkillRepository", lambda roots: repository)

    dialog = chat_actions.build_session_skills_dialog(None, history, config, "session-1")
    try:
        assert isinstance(dialog, QDialog)
        assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert dialog.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        assert dialog.findChild(QFrame, "frameless_dialog_panel") is not None
        close_button = dialog.findChild(QPushButton, "session_skills_close_button")
        assert close_button is not None
        assert close_button.accessibleName() == "Close session skills"
        assert close_button.toolTip() == "关闭会话技能"
        close_button.click()
        assert dialog.result() == QDialog.DialogCode.Rejected
    finally:
        dialog.close()


def test_session_manager_dialog_uses_project_drawn_frameless_chrome(app):
    window = ChatUIWindow()
    window.set_session_list(
        [
            {"id": "session-1", "title": "雨夜咖啡馆", "archived": False},
            {"id": "session-2", "title": "旧校舍调查", "archived": True},
        ],
        "session-1",
    )
    try:
        dialog = window._build_session_manager_dialog()
        assert isinstance(dialog, QDialog)
        assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert dialog.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        assert dialog.findChild(QFrame, "frameless_dialog_panel") is not None
        close_button = dialog.findChild(QPushButton, "session_manager_close_button")
        assert close_button is not None
        assert close_button.accessibleName() == "Close session manager"
        assert close_button.toolTip() == "关闭会话管理"
        close_button.click()
        assert dialog.result() == QDialog.DialogCode.Rejected
    finally:
        window.close()
