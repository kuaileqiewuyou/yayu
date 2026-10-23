import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QRect, QSize, Qt
from PySide6.QtGui import QCursor, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QFrame, QLabel, QPushButton

from ui.chat_ui.chat_ui import ChatHistoryEntry, ChatUIWindow, SpriteWidget
from ui.theme import CHAT_DIALOGUE_GLASS_STYLE, CHAT_TEMPORARY_CONTENT_GLASS_STYLE


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


def test_main_window_layers_fullscreen_stage_below_floating_dialog(app):
    window = ChatUIWindow()
    try:
        assert window.character_stage.objectName() == "character_stage"
        assert window.current_message_frame.objectName() == "current_message_frame"
        assert window.character_stage_layout.indexOf(window.sprite_widget) >= 0
        # 立绘层铺满窗口，悬浮 UI 层压在其上
        assert window._stack.indexOf(window.character_stage) == 0
        assert window._stack.indexOf(window.overlay_layer) == 1
        # 悬浮对话单元挂在 overlay 层底部
        assert window.overlay_layer.isAncestorOf(window.dialog_unit)
        assert window.main_content_layout.indexOf(window.dialog_unit.parent()) > window.main_content_layout.indexOf(
            window.top_chrome
        )
        assert not hasattr(window, "messages_layout")
    finally:
        window.close()


def test_top_right_history_and_settings_controls_are_accessible(app):
    window = ChatUIWindow()
    emitted = []
    window.settings_requested.connect(lambda: emitted.append("settings"))
    try:
        assert window.history_btn.objectName() == "history_button"
        assert window.history_btn.accessibleName() == "Open chat history"
        assert window.history_btn.toolTip() == "查看聊天记录"
        assert window.settings_btn.objectName() == "settings_button"
        assert window.settings_btn.accessibleName() == "Open settings"
        assert window.settings_btn.toolTip() == "打开设置中心"
        assert window.history_btn.minimumWidth() >= 40
        assert window.history_btn.minimumHeight() >= 40
        assert window.settings_btn.minimumWidth() >= 40
        assert window.settings_btn.minimumHeight() >= 40
        window.settings_btn.click()
        assert emitted == ["settings"]
    finally:
        window.close()


def test_top_right_window_controls_keep_existing_size_and_order(app):
    window = ChatUIWindow()
    try:
        controls = [window.history_btn, window.background_btn, window.settings_btn, window.minimize_btn, window.close_btn]
        assert [button.property("icon_name") for button in controls] == ["history", "image", "settings", "minus", "close"]
        assert [(button.width(), button.height()) for button in controls] == [(40, 40)] * 5
    finally:
        window.close()


def test_dialogue_triangle_toggles_non_layout_conversation_info_popup(app):
    window = ChatUIWindow()
    window.set_session_list(
        [{"id": "s1", "title": "雨夜咖啡馆", "archived": False, "enabled_skills": []}],
        "s1",
    )
    window.add_message("我会陪你等到雨停。", char_name="诺艾尔")
    window.set_reply_status("会话记忆已启用")
    try:
        toggle = window.dialog_info_toggle_btn
        popup = window.conversation_info_popup
        assert isinstance(toggle, QPushButton)
        assert toggle.property("icon_name") == "info"
        assert toggle.accessibleName() == "Toggle conversation information"
        assert toggle.toolTip() == "查看运行过程与服务状态"
        assert toggle.minimumWidth() >= 24
        assert toggle.minimumHeight() >= 24
        assert popup.windowFlags() & Qt.WindowType.Popup
        assert not popup.isVisible()
        assert window.reply_status_label.text() == "会话记忆已启用"
        assert window.runtime_state_badge_label.text() == "已完成"
        assert window.conversation_info_layout.indexOf(window.runtime_activity_frame) >= 0
        assert window.conversation_info_layout.indexOf(window.current_character_info_label) == -1
        assert window.conversation_info_layout.indexOf(window.session_title_label) == -1
        assert window.current_character_info_label.isHidden()
        assert window.session_title_label.isHidden()
        assert window.chat_layout.indexOf(window.reply_status_label) == -1

        window.show()
        app.processEvents()
        toggle.click()
        app.processEvents()
        assert popup.isVisible()
        assert toggle.property("icon_name") == "close"
        popup.hide()
        app.processEvents()
        assert not popup.isVisible()
        assert toggle.property("icon_name") == "info"
        toggle.click()
        app.processEvents()
        assert popup.isVisible()
        toggle.click()
        app.processEvents()
        assert not popup.isVisible()
        assert toggle.property("icon_name") == "info"
    finally:
        window.close()


def test_real_second_triangle_click_cannot_reopen_popup_from_same_mouse_event(app):
    window = ChatUIWindow()
    try:
        window.show()
        app.processEvents()
        toggle = window.dialog_info_toggle_btn
        popup = window.conversation_info_popup

        QTest.mouseClick(toggle, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert popup.isVisible()

        QTest.mouseClick(toggle, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert not popup.isVisible()
        assert toggle.property("icon_name") == "info"

        QTest.mouseClick(toggle, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert popup.isVisible()
        assert toggle.property("icon_name") == "close"
    finally:
        window.close()


def test_popup_auto_hide_over_triangle_suppresses_replayed_click(app, monkeypatch):
    window = ChatUIWindow()
    try:
        window.show()
        app.processEvents()
        toggle = window.dialog_info_toggle_btn
        popup = window.conversation_info_popup
        toggle.click()
        app.processEvents()
        assert popup.isVisible()

        cursor_position = toggle.mapToGlobal(toggle.rect().center())
        monkeypatch.setattr(QCursor, "pos", staticmethod(lambda: cursor_position))
        popup.hide()
        assert not popup.isVisible()

        toggle.click()
        app.processEvents()
        assert not popup.isVisible()
        assert toggle.property("icon_name") == "info"
    finally:
        window.close()


def test_popup_auto_hide_suppression_expires_without_replayed_click(app, monkeypatch):
    window = ChatUIWindow()
    try:
        window.show()
        app.processEvents()
        toggle = window.dialog_info_toggle_btn
        popup = window.conversation_info_popup
        toggle.click()
        app.processEvents()
        assert popup.isVisible()

        cursor_position = toggle.mapToGlobal(toggle.rect().center())
        monkeypatch.setattr(QCursor, "pos", staticmethod(lambda: cursor_position))
        popup.hide()
        assert not popup.isVisible()

        QTest.qWait(300)
        toggle.click()
        app.processEvents()
        assert popup.isVisible()
    finally:
        window.close()


def test_conversation_info_popup_geometry_flips_and_fits_screen(app):
    window = ChatUIWindow()
    try:
        screen = QRect(100, 50, 800, 600)
        popup_size = QSize(420, 260)

        below = window._conversation_info_popup_geometry(
            QRect(700, 100, 40, 40), popup_size, screen
        )
        assert below == QRect(320, 144, 420, 260)

        above = window._conversation_info_popup_geometry(
            QRect(700, 580, 40, 40), popup_size, screen
        )
        assert above == QRect(320, 316, 420, 260)

        clamped = window._conversation_info_popup_geometry(
            QRect(50, 20, 40, 40), QSize(900, 700), screen
        )
        assert clamped == screen
        assert screen.contains(clamped)

        narrow_screen = QRect(100, 50, 300, 600)
        narrow_geometry = window._conversation_info_popup_geometry(
            QRect(340, 100, 40, 40), popup_size, narrow_screen
        )
        window.conversation_info_popup.setGeometry(narrow_geometry)
        assert narrow_screen.contains(window.conversation_info_popup.geometry())
    finally:
        window.close()


def test_default_chat_geometry_gives_character_stage_more_room(app):
    window = ChatUIWindow()
    try:
        window.show()
        app.processEvents()
        assert window.height() >= 640
        # 全屏立绘：舞台铺满整个窗口
        assert window.character_stage.height() >= window.height() - 8
        # 悬浮对话框保持紧凑，不挤占立绘
        assert window.current_message_frame.maximumHeight() <= 150
        assert window.character_stage.height() > window.current_message_frame.height() * 2
    finally:
        window.close()


def test_latest_message_replaces_stage_dialogue_while_history_keeps_order(app):
    window = ChatUIWindow()
    try:
        window.add_message("第一句", is_user=True)
        window.add_message("第二句", char_name="诺艾尔", char_color="#ABCDEF")
        assert window.current_speaker_label.text() == "诺艾尔"
        assert window.current_message_label.text() == "第二句"
        assert window.message_history_snapshot() == [
            {"text": "第一句", "is_user": True, "char_name": "", "char_color": "#f2a0bd"},
            {"text": "第二句", "is_user": False, "char_name": "诺艾尔", "char_color": "#ABCDEF"},
        ]
    finally:
        window.close()


def test_history_dialog_renders_all_messages_without_mutating_stage(app):
    window = ChatUIWindow()
    try:
        window.add_message("你好", is_user=True)
        window.add_message("我在哦", char_name="诺艾尔")
        window.input_edit.setText("未发送草稿")
        dialog = window._build_chat_history_dialog()
        assert isinstance(dialog, QDialog)
        rows = dialog.findChildren(QLabel, "history_message_text")
        assert [row.text() for row in rows] == ["你好", "我在哦"]
        dialog.close()
        assert window.current_message_label.text() == "我在哦"
        assert window.input_edit.text() == "未发送草稿"
    finally:
        window.close()


def test_history_dialog_is_frameless_and_has_project_drawn_close_control(app):
    window = ChatUIWindow()
    try:
        dialog = window._build_chat_history_dialog()
        assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
        button = dialog.findChild(QPushButton, "history_close_button")
        assert button is not None
        assert button.accessibleName() == "Close history"
        assert button.toolTip() == "关闭聊天记录"
        dialog.close()
    finally:
        window.close()


def test_history_dialog_keeps_opaque_panel_inside_translucent_frameless_window(app):
    window = ChatUIWindow()
    try:
        window.add_message("用于检查聊天记录面板背景。", char_name="诺艾尔")
        dialog = window._build_chat_history_dialog()
        dialog.show()
        app.processEvents()

        panel = dialog.findChild(QFrame, "history_panel")
        assert panel is not None
        assert panel.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        image = dialog.grab().toImage()
        background = image.pixelColor(dialog.width() // 2, dialog.height() - 24)
        assert background.alpha() >= 240

        dialog.close()
    finally:
        window.close()


def test_history_dialog_has_empty_state(app):
    window = ChatUIWindow()
    try:
        dialog = window._build_chat_history_dialog()
        empty = dialog.findChild(QLabel, "history_empty_state")
        assert empty is not None
        assert empty.text() == "还没有聊天记录"
        dialog.close()
    finally:
        window.close()


def test_stream_updates_one_current_message_and_one_history_entry(app):
    window = ChatUIWindow()
    try:
        window.begin_stream(char_name="诺艾尔", char_color="#ABCDEF")
        window.append_stream("你")
        window.append_stream("好")
        assert window.current_message_label.text() == "你好"
        assert window.message_history_snapshot() == [
            {"text": "你好", "is_user": False, "char_name": "诺艾尔", "char_color": "#ABCDEF"}
        ]
        window.end_stream()
        assert window.current_message_label.text() == "你好"
    finally:
        window.close()


def test_empty_stream_and_clear_leave_no_visible_or_historical_message(app):
    window = ChatUIWindow()
    try:
        window.begin_stream(char_name="诺艾尔")
        window.end_stream()
        assert window.message_history_snapshot() == []
        assert window.current_message_label.text() == ""
        window.add_message("临时消息")
        window.clear_messages()
        assert window.message_history_snapshot() == []
        assert window.current_message_label.text() == ""
        assert window.current_speaker_label.text() == ""
    finally:
        window.close()


def test_sprite_display_is_bounded_by_available_width_and_height(app):
    sprite = SpriteWidget()
    sprite.resize(QSize(320, 240))
    source = QPixmap(1200, 300)
    source.fill()
    sprite._source_pixmap = source
    sprite._scale = 1.5
    sprite._update_display()
    rendered = sprite.pixmap()
    assert rendered is not None
    assert rendered.width() <= sprite.width()
    assert rendered.height() <= sprite.height()


def test_sprite_keeps_last_valid_image_when_next_path_is_missing_or_invalid(app, tmp_path):
    valid_path = tmp_path / "valid.png"
    source = QPixmap(80, 120)
    source.fill()
    assert source.save(str(valid_path))
    invalid_path = tmp_path / "invalid.png"
    invalid_path.write_text("not an image", encoding="utf-8")

    sprite = SpriteWidget()
    sprite.resize(QSize(320, 240))
    assert sprite.set_sprite(str(valid_path)) is True
    valid_cache_key = sprite.pixmap().cacheKey()

    assert sprite.set_sprite(str(tmp_path / "missing.png")) is False
    assert sprite.pixmap().cacheKey() == valid_cache_key
    assert sprite.set_sprite(str(invalid_path)) is False
    assert sprite.pixmap().cacheKey() == valid_cache_key


def test_sprite_first_failed_load_leaves_empty_stage(app, tmp_path):
    sprite = SpriteWidget()
    assert sprite.set_sprite(str(tmp_path / "missing.png")) is False
    assert sprite.pixmap().isNull()


def test_long_dialogue_and_tool_summary_are_height_bounded(app):
    window = ChatUIWindow()
    try:
        window.add_message("很长的对白。" * 500, char_name="诺艾尔")
        assert window.current_message_frame.maximumHeight() <= 180
        assert window.current_message_scroll_area.widget() is window.current_message_label
        assert window.tool_summary_scroll_area.maximumHeight() <= 180
    finally:
        window.close()


def test_history_and_settings_remain_available_while_waiting(app):
    window = ChatUIWindow()
    try:
        window.set_waiting_for_reply(True)
        assert window.history_btn.isEnabled()
        assert window.settings_btn.isEnabled()
        assert not window.reroll_btn.isEnabled()
    finally:
        window.close()


def test_discard_stream_removes_provisional_raw_payload(app):
    window = ChatUIWindow()
    try:
        window.begin_stream(char_name="诺艾尔")
        window.append_stream('{"dialog": "协议原文"}')
        window.discard_stream()
        window.add_message("正式对白", char_name="诺艾尔")
        assert window.message_history_snapshot() == [
            {"text": "正式对白", "is_user": False, "char_name": "诺艾尔", "char_color": "#f2a0bd"}
        ]
    finally:
        window.close()


def test_glass_styles_and_temporary_content_use_semantic_anchors(app):
    window = ChatUIWindow()
    try:
        assert window.current_message_frame.styleSheet() == CHAT_DIALOGUE_GLASS_STYLE
        assert window.temporary_content_scroll_area.objectName() == "temporary_content_scroll_area"
        assert window.temporary_content_scroll_area.accessibleName() == "Temporary conversation content"
        assert window.temporary_content_scroll_area.styleSheet() == CHAT_TEMPORARY_CONTENT_GLASS_STYLE
        assert window.temporary_content_widget.objectName() == "temporary_content_widget"
        assert window.temporary_content_widget.accessibleName() == "Temporary conversation content"
    finally:
        window.close()


def test_history_dialog_consumes_a_defensive_snapshot(app):
    window = ChatUIWindow()
    try:
        window.add_message("快照消息", char_name="诺艾尔")
        snapshot = window.message_history_snapshot()
        snapshot[0]["text"] = "外部篡改"
        dialog = window._build_chat_history_dialog()
        rows = dialog.findChildren(QLabel, "history_message_text")
        assert [row.text() for row in rows] == ["快照消息"]
        dialog.close()
    finally:
        window.close()


def test_history_dialog_long_bubbles_expand_to_full_wrapped_height(app):
    window = ChatUIWindow()
    try:
        window.add_message("很长的历史消息，用于验证完整换行高度。" * 30, char_name="诺艾尔")
        window.add_message("第二条消息也不能覆盖上一条。" * 12, is_user=True)
        dialog = window._build_chat_history_dialog()
        dialog.show()
        app.processEvents()
        bubbles = dialog.findChildren(QLabel, "history_message_text")
        assert len(bubbles) == 2
        for bubble in bubbles:
            assert bubble.height() >= bubble.heightForWidth(bubble.width())
            assert bubble.height() > bubble.fontMetrics().height() * 2
        first_bottom = bubbles[0].mapTo(dialog, bubbles[0].rect().bottomLeft()).y()
        second_top = bubbles[1].mapTo(dialog, bubbles[1].rect().topLeft()).y()
        assert second_top > first_bottom
        dialog.close()
    finally:
        window.close()


def test_chat_history_entry_owns_speaker_presentation_and_snapshot_shape():
    entry = ChatHistoryEntry(text="你好", is_user=True, char_color="#ABCDEF")
    assert entry.speaker_name == "你"
    assert entry.to_snapshot() == {
        "text": "你好",
        "is_user": True,
        "char_name": "",
        "char_color": "#ABCDEF",
    }
