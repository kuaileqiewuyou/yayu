import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ui.chat_ui.chat_ui import ChatUIWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def dispose_closed_chat_windows(app):
    yield
    for window in app.topLevelWidgets():
        if isinstance(window, ChatUIWindow):
            window.close()
            window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_companion_toggle_button_is_small_and_always_on_top(app):
    window = ChatUIWindow()
    try:
        btn = window.companion_toggle_btn
        assert btn.objectName() == "companion_toggle_button"
        assert btn.accessibleName() == "Toggle interface visibility"
        # 小巧：不超过 24px，避免影响立绘观感
        assert btn.width() <= 24
        assert btn.height() <= 24
        # 默认界面可见，按钮显示「收起」语义
        assert window._ui_visible is True
        assert btn.property("icon_name") == "eye"
        assert "收起" in btn.toolTip()
    finally:
        window.close()


def test_toggle_hides_everything_except_sprite_and_itself(app):
    window = ChatUIWindow()
    window.add_message("测试台词", char_name="诺艾尔")
    window.show()
    app.processEvents()
    try:
        window.companion_toggle_btn.click()
        QTest.qWait(260)
        app.processEvents()

        assert window._ui_visible is False
        assert not window.overlay_layer.isVisible()
        # 立绘与常驻开关保持可见
        assert window.character_stage.isVisible()
        assert window.companion_toggle_btn.isVisible()
        assert window.companion_toggle_btn.property("icon_name") == "eye-off"
        assert "展开" in window.companion_toggle_btn.toolTip()

        window.companion_toggle_btn.click()
        QTest.qWait(260)
        app.processEvents()
        assert window._ui_visible is True
        assert window.overlay_layer.isVisible()
        assert window.companion_toggle_btn.property("icon_name") == "eye"
    finally:
        window.close()


def test_new_message_auto_shows_ui_when_hidden(app):
    window = ChatUIWindow()
    window.show()
    app.processEvents()
    try:
        window._set_ui_visible(False)
        QTest.qWait(260)
        app.processEvents()
        assert not window.overlay_layer.isVisible()

        # 她说话 / 发起流式回复时，界面自动展开
        window.add_message("我回来啦", char_name="诺艾尔")
        QTest.qWait(260)
        app.processEvents()
        assert window.overlay_layer.isVisible()
        assert window._ui_visible is True
    finally:
        window.close()


def test_begin_stream_auto_shows_ui_when_hidden(app):
    window = ChatUIWindow()
    window.show()
    app.processEvents()
    try:
        window._set_ui_visible(False)
        QTest.qWait(260)
        app.processEvents()
        assert not window.overlay_layer.isVisible()

        window.begin_stream(char_name="诺艾尔")
        QTest.qWait(260)
        app.processEvents()
        assert window.overlay_layer.isVisible()
    finally:
        window.close()


def test_toggle_button_follows_top_bar_group_on_resize(app):
    window = ChatUIWindow()
    window.show()
    app.processEvents()
    try:
        btn = window.companion_toggle_btn
        group_width = 5 * 40 + 4 * 6
        expected_x = window.width() - 12 - group_width - 6 - btn.width()
        assert btn.x() == expected_x
        old_x = btn.x()
        window.resize(window.width() + 120, window.height())
        app.processEvents()
        assert btn.x() == old_x + 120
        assert btn.x() == window.width() - 12 - group_width - 6 - btn.width()
    finally:
        window.close()


def test_companion_toggle_sits_left_of_top_bar_group_without_overlap(app):
    window = ChatUIWindow()
    window.show()
    app.processEvents()
    try:
        # 常驻开关位于 ☰（按钮组最左）之左，互不重叠，远离 ✕
        btn = window.companion_toggle_btn
        toggle_right = btn.x() + btn.width()
        history_left = window.history_btn.mapTo(window, window.history_btn.rect().topLeft()).x()
        assert toggle_right <= history_left
        close_left = window.close_btn.mapTo(window, window.close_btn.rect().topLeft()).x()
        assert toggle_right < close_left
    finally:
        window.close()
