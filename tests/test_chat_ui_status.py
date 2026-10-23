import os
import struct
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QMessageBox
import pytest

from ui.chat_ui.chat_ui import ChatUIWindow


def _minimal_png_rgba(width: int = 1, height: int = 1) -> bytes:
    """Return a tiny valid RGBA PNG generated locally for CG preview tests."""
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        payload = kind + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + (b"\xff\xff\xff\xff" * width) for _ in range(height))
    return b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
            chunk(b"IDAT", zlib.compress(raw)),
            chunk(b"IEND", b""),
        ]
    )


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def cleanup_chat_ui_windows():
    """Dispose ChatUIWindow instances created by these tests before the shared app is reused."""
    yield

    app = QApplication.instance()
    if app is None:
        return
    windows = [widget for widget in app.topLevelWidgets() if isinstance(widget, ChatUIWindow)]
    for window in windows:
        window.close()
        window.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


class _FakeLeftClickEvent:
    def button(self):
        return Qt.MouseButton.LeftButton

    def accept(self):
        pass


def test_runtime_activity_replaces_redundant_session_context_in_on_demand_popup():
    _app()
    window = ChatUIWindow()

    assert window.reply_status_label.text() == "准备就绪，等待消息"
    assert window.runtime_state_badge_label.text() == "空闲"
    assert window.runtime_activity_frame.accessibleName() == "Runtime activity"
    assert window.runtime_activity_scroll_area.maximumHeight() <= 150
    assert window.conversation_info_layout.indexOf(window.runtime_activity_frame) >= 0
    assert window.conversation_info_layout.indexOf(window.session_title_label) == -1
    assert window.conversation_info_layout.indexOf(window.rename_session_btn) == -1
    assert window.conversation_info_layout.indexOf(window.archive_session_btn) == -1
    assert window.session_title_label.isHidden()
    assert window.rename_session_btn.isHidden()
    assert window.archive_session_btn.isHidden()
    assert window.chat_layout.indexOf(window.input_frame) >= 0


def test_set_reply_status_updates_text_and_error_style_without_large_space():
    _app()
    window = ChatUIWindow()

    window.set_reply_status("模型思考中...")
    assert window.reply_status_label.text() == "模型思考中..."
    assert window.reply_status_label.maximumHeight() <= 44
    assert "rgba(35, 48, 57" in window.reply_status_label.styleSheet()

    window.set_reply_status("回复失败：401 Unauthorized", error=True)
    assert window.reply_status_label.text() == "回复失败：401 Unauthorized"
    assert "rgba(173, 81, 74" in window.reply_status_label.styleSheet()

    window.clear_reply_status()
    assert window.reply_status_label.text() == ""


def test_set_session_list_updates_current_session_title_label():
    _app()
    window = ChatUIWindow()

    window.set_session_list(
        [
            {"id": "s1", "title": "默认会话", "archived": False, "enabled_skills": []},
            {"id": "s2", "title": "第二会话", "archived": True, "enabled_skills": ["mystery"]},
        ],
        active_session_id="s2",
    )

    assert window.current_session_id == "s2"
    assert window.current_session_title == "第二会话"
    assert window.session_title_label.text() == "当前会话：第二会话"
    assert window._session_items[1]["archived"] is True
    assert window._session_items[1]["enabled_skills"] == ["mystery"]


def test_current_session_action_buttons_exist_and_are_enabled_by_default():
    _app()
    window = ChatUIWindow()

    assert window.rename_session_btn.text() == "重命名当前会话"
    assert window.archive_session_btn.text() == "归档当前会话"
    assert window.rename_session_btn.isEnabled()
    assert window.archive_session_btn.isEnabled()


def test_set_config_notice_points_to_settings_button():
    _app()
    window = ChatUIWindow()

    window.set_config_notice("LLM 配置不完整：API Key。请先在设置中补全后再开始对话。")

    assert window.reply_status_label.text() == (
        "LLM 配置不完整：API Key。请先在设置中补全后再开始对话。"
        " 请点击下方「设置」补全配置。"
    )
    assert "rgba(173, 81, 74" in window.reply_status_label.styleSheet()
    assert "打开设置中心" in window.settings_btn.toolTip()


def test_empty_stream_placeholder_is_removed_before_final_dialog_bubble():
    _app()
    window = ChatUIWindow()

    window.begin_stream(char_name="诺艾尔", char_color="#f2a0bd")
    window.end_stream()
    window.add_message("你好呀", is_user=False, char_name="诺艾尔", char_color="#f2a0bd")

    assert window.message_history_snapshot() == [
        {"text": "你好呀", "is_user": False, "char_name": "诺艾尔", "char_color": "#f2a0bd"}
    ]
    assert window.current_speaker_label.text() == "诺艾尔"


def test_send_controls_disable_while_waiting_and_reenable_after_completion_or_error():
    _app()
    window = ChatUIWindow()

    assert window.send_btn.isEnabled()
    assert window.input_edit.isEnabled()

    window.set_waiting_for_reply(True)
    assert not window.send_btn.isEnabled()
    assert not window.input_edit.isEnabled()
    assert "正在回复" in window.send_btn.text()

    window.set_waiting_for_reply(False)
    assert window.send_btn.isEnabled()
    assert window.input_edit.isEnabled()
    assert window.send_btn.text() == "发送"

    window.set_waiting_for_reply(True)
    window.set_reply_status("回复失败：测试错误", error=True)
    window.set_waiting_for_reply(False)
    assert window.send_btn.isEnabled()
    assert window.input_edit.isEnabled()


def test_conversation_action_buttons_emit_clear_and_reroll_signals(monkeypatch):
    _app()
    window = ChatUIWindow()
    emitted = []
    question_calls = []

    def fake_question(parent, title, text, buttons, default_button):
        question_calls.append({
            "parent": parent,
            "title": title,
            "text": text,
            "buttons": buttons,
            "default_button": default_button,
        })
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", fake_question)
    window.clear_requested.connect(lambda: emitted.append("clear"))
    window.reroll_requested.connect(lambda: emitted.append("reroll"))
    window.settings_requested.connect(lambda: emitted.append("settings"))

    window.clear_btn.click()
    window.reroll_btn.click()
    window.settings_btn.click()

    assert window.reroll_btn.toolTip() == "重发上一条消息"
    assert emitted == ["clear", "reroll", "settings"]
    assert question_calls == [{
        "parent": window,
        "title": "确认重发",
        "text": "确定要重发上一条消息吗？",
        "buttons": QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        "default_button": QMessageBox.StandardButton.No,
    }]


def test_reroll_button_does_not_emit_when_confirmation_rejected(monkeypatch):
    _app()
    window = ChatUIWindow()
    emitted = []

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    window.reroll_requested.connect(lambda: emitted.append("reroll"))

    window.reroll_btn.click()

    assert emitted == []


def test_waiting_state_keeps_navigation_available_while_disabling_mutations():
    _app()
    window = ChatUIWindow()

    assert window.clear_btn.isEnabled()
    assert window.reroll_btn.isEnabled()
    assert window.settings_btn.isEnabled()
    assert window.open_cg_generated_dir_btn.isEnabled()
    assert window.close_btn.isEnabled()

    window.set_waiting_for_reply(True)

    assert not window.clear_btn.isEnabled()
    assert not window.reroll_btn.isEnabled()
    assert window.settings_btn.isEnabled()
    assert window.history_btn.isEnabled()
    assert not window.open_cg_generated_dir_btn.isEnabled()
    assert window.close_btn.isEnabled()

    window.set_waiting_for_reply(False)

    assert window.clear_btn.isEnabled()
    assert window.reroll_btn.isEnabled()
    assert window.settings_btn.isEnabled()
    assert window.open_cg_generated_dir_btn.isEnabled()
    assert window.close_btn.isEnabled()


def test_add_cg_preview_appends_loadable_image_to_messages(tmp_path):
    _app()
    image_path = tmp_path / "cg.png"
    image_path.write_bytes(_minimal_png_rgba(width=2, height=2))
    window = ChatUIWindow()

    result = window.add_cg_preview(str(image_path))

    assert result is True
    assert window.last_cg_preview_path == str(image_path)
    labels = window.messages_widget.findChildren(QLabel)
    assert any(label.text().startswith("CG") for label in labels)
    assert any(label.pixmap() is not None and not label.pixmap().isNull() for label in labels)


def test_add_cg_preview_records_preview_label_with_image_path(tmp_path):
    _app()
    image_path = tmp_path / "cg.png"
    image_path.write_bytes(_minimal_png_rgba(width=4, height=4))
    window = ChatUIWindow()

    assert window.add_cg_preview(str(image_path)) is True

    assert window.last_cg_preview_path == str(image_path)
    assert len(window._cg_preview_labels) == 1
    label = window._cg_preview_labels[0]
    assert label.image_path == str(image_path)
    assert label.pixmap() is not None
    assert not label.pixmap().isNull()


def test_cg_preview_title_includes_filename(tmp_path):
    _app()
    image_path = tmp_path / "sunset.png"
    image_path.write_bytes(_minimal_png_rgba(width=4, height=4))
    window = ChatUIWindow()

    window.add_cg_preview(str(image_path))

    labels = window.messages_widget.findChildren(QLabel)
    assert any("sunset.png" in label.text() for label in labels)


def test_new_session_preset_options_include_builtins_and_user_presets(monkeypatch):
    _app()
    window = ChatUIWindow()
    window.skill_preset_options = ["全选", "全局默认", "推理"]
    emitted = []

    class FakeDialog:
        def __init__(self, parent=None):
            self.parent = parent

        def setWindowTitle(self, title):
            self.title = title

        def resize(self, width, height):
            self.size = (width, height)

        def accept(self):
            self.accepted = True

        def reject(self):
            self.rejected = True

        def exec(self):
            return 0

    class FakeVBoxLayout:
        instances = []

        def __init__(self, parent=None):
            self.parent = parent
            self.widgets = []
            FakeVBoxLayout.instances.append(self)

        def addWidget(self, widget):
            self.widgets.append(widget)

        def addLayout(self, layout):
            self.widgets.append(layout)

    class FakeHBoxLayout:
        def __init__(self, parent=None):
            self.parent = parent
            self.widgets = []

        def addWidget(self, widget):
            self.widgets.append(widget)

        def addStretch(self):
            self.widgets.append("stretch")

    class FakeListWidget:
        def __init__(self, parent=None):
            self.items = []
            self._current_row = 0
            self.itemDoubleClicked = FakePushButton._Signal()

        def addItem(self, text):
            self.items.append(text)

        def setCurrentRow(self, row):
            self._current_row = row

        def currentItem(self):
            if not self.items:
                return None
            selected_text = self.items[self._current_row]
            return type("Item", (), {"text": lambda self_item: selected_text})()

    class FakePushButton:
        instances = []

        class _Signal:
            def __init__(self):
                self.callback = None

            def connect(self, callback):
                self.callback = callback

        def __init__(self, text):
            self.text = text
            self.clicked = self._Signal()
            FakePushButton.instances.append(self)

        def setObjectName(self, name):
            self.object_name = name

    import ui.chat_ui.chat_ui as chat_ui_module

    monkeypatch.setattr(chat_ui_module, "QDialog", FakeDialog)
    monkeypatch.setattr(chat_ui_module, "QVBoxLayout", FakeVBoxLayout)
    monkeypatch.setattr(chat_ui_module, "QHBoxLayout", FakeHBoxLayout)
    monkeypatch.setattr(chat_ui_module, "QListWidget", FakeListWidget)
    monkeypatch.setattr(chat_ui_module, "QPushButton", FakePushButton)
    monkeypatch.setattr(
        chat_ui_module,
        "build_frameless_dialog_shell",
        lambda dialog, title, **kwargs: FakeVBoxLayout(dialog),
    )

    window.new_session_requested.connect(lambda preset_name: emitted.append(preset_name))

    window._open_session_manager()

    list_widgets = [widget for widget in FakeVBoxLayout.instances[0].widgets if isinstance(widget, FakeListWidget)]
    preset_list_widget = next(widget for widget in list_widgets if widget.items[:3] == ["全选", "全局默认", "推理"])

    assert preset_list_widget.items[:3] == ["全选", "全局默认", "推理"]

    new_button = next(button for button in FakePushButton.instances if button.text == "新建")
    new_button.clicked.callback()

    assert emitted == ["全选"]


def test_cg_preview_label_click_invokes_open_callback(tmp_path):
    _app()
    image_path = tmp_path / "cg.png"
    image_path.write_bytes(_minimal_png_rgba(width=4, height=4))
    opened = []
    window = ChatUIWindow()
    window._open_cg_preview = opened.append

    assert window.add_cg_preview(str(image_path)) is True
    label = window._cg_preview_labels[0]

    label.mousePressEvent(_FakeLeftClickEvent())

    assert opened == [str(image_path)]


def test_cg_preview_includes_open_and_copy_path_buttons(tmp_path):
    _app()
    image_path = tmp_path / "cg.png"
    image_path.write_bytes(_minimal_png_rgba(width=4, height=4))
    window = ChatUIWindow()

    assert window.add_cg_preview(str(image_path)) is True

    button_texts = [button.text() for button in window.messages_widget.findChildren(QPushButton)]
    assert "打开图片" in button_texts
    assert "复制路径" in button_texts


def test_cg_preview_copy_path_button_copies_path_and_sets_status(tmp_path):
    _app()
    image_path = tmp_path / "cg.png"
    image_path.write_bytes(_minimal_png_rgba(width=4, height=4))
    copied = []
    window = ChatUIWindow()
    window._copy_text_to_clipboard = copied.append

    assert window.add_cg_preview(str(image_path)) is True
    button = next(button for button in window.messages_widget.findChildren(QPushButton) if button.text() == "复制路径")

    button.click()

    assert copied == [str(image_path)]
    assert window.reply_status_label.text() == f"已复制 CG 图片路径：{image_path}"
    assert "rgba(35, 48, 57" in window.reply_status_label.styleSheet()


def test_cg_preview_open_image_button_opens_local_image_and_sets_success_status(tmp_path):
    _app()
    image_path = tmp_path / "cg.png"
    image_path.write_bytes(_minimal_png_rgba(width=4, height=4))
    opened = []
    window = ChatUIWindow()
    window._open_local_path = lambda path: opened.append(path) or True

    assert window.add_cg_preview(str(image_path)) is True
    buttons = [button for button in window.messages_widget.findChildren(QPushButton) if button.text() == "打开图片"]
    assert len(buttons) == 1

    buttons[0].click()

    assert opened == [image_path]
    assert window.reply_status_label.text() == f"已打开 CG 图片：{image_path}"
    assert "rgba(35, 48, 57" in window.reply_status_label.styleSheet()


def test_cg_preview_open_image_button_sets_error_status_when_open_fails(tmp_path):
    _app()
    image_path = tmp_path / "cg.png"
    image_path.write_bytes(_minimal_png_rgba(width=4, height=4))
    window = ChatUIWindow()
    window._open_local_path = lambda path: False

    assert window.add_cg_preview(str(image_path)) is True
    button = next(button for button in window.messages_widget.findChildren(QPushButton) if button.text() == "打开图片")

    button.click()

    assert window.reply_status_label.text() == f"打开 CG 图片失败：{image_path}"
    assert "rgba(173, 81, 74" in window.reply_status_label.styleSheet()


def test_cg_preview_open_image_button_catches_open_oserror_and_sets_error_status(tmp_path):
    _app()
    image_path = tmp_path / "cg.png"
    image_path.write_bytes(_minimal_png_rgba(width=4, height=4))
    window = ChatUIWindow()

    def fail_open(path):
        raise OSError("open denied")

    window._open_local_path = fail_open

    assert window.add_cg_preview(str(image_path)) is True
    button = next(button for button in window.messages_widget.findChildren(QPushButton) if button.text() == "打开图片")

    button.click()

    assert window.reply_status_label.text() == f"打开 CG 图片失败：{image_path}（open denied）"
    assert "rgba(173, 81, 74" in window.reply_status_label.styleSheet()


def test_open_cg_preview_builds_dialog_for_loadable_image(tmp_path):
    _app()
    image_path = tmp_path / "cg.png"
    image_path.write_bytes(_minimal_png_rgba(width=8, height=8))
    window = ChatUIWindow()

    dialog = window._build_cg_preview_dialog(str(image_path))

    assert dialog.windowTitle().endswith("cg.png")
    labels = dialog.findChildren(QLabel)
    assert any(label.pixmap() is not None and not label.pixmap().isNull() for label in labels)


def test_build_cg_preview_dialog_returns_none_for_unloadable_image(tmp_path):
    _app()
    bad_path = tmp_path / "bad.png"
    bad_path.write_text("not image", encoding="utf-8")
    window = ChatUIWindow()

    assert window._build_cg_preview_dialog(str(bad_path)) is None


def test_refresh_cg_preview_sizes_updates_live_labels_and_prunes_removed(tmp_path):
    _app()
    image_path = tmp_path / "cg.png"
    image_path.write_bytes(_minimal_png_rgba(width=16, height=16))
    window = ChatUIWindow()
    assert window.add_cg_preview(str(image_path)) is True
    live_label = window._cg_preview_labels[0]
    calls = []
    live_label.set_preview_width = calls.append

    class RemovedLabel:
        def parent(self):
            return None

        def set_preview_width(self, width):
            raise AssertionError("removed labels should not be resized")

    removed_label = RemovedLabel()
    window._cg_preview_labels.append(removed_label)

    window._refresh_cg_preview_sizes()

    assert calls == [window._cg_preview_width()]
    assert window._cg_preview_labels == [live_label]


def test_resize_event_refreshes_cg_preview_widths(tmp_path):
    _app()
    image_path = tmp_path / "cg.png"
    image_path.write_bytes(_minimal_png_rgba(width=16, height=16))
    window = ChatUIWindow()
    assert window.add_cg_preview(str(image_path)) is True
    label = window._cg_preview_labels[0]
    calls = []
    label.set_preview_width = calls.append

    window.resizeEvent(None)

    assert calls == [window._cg_preview_width()]


def test_add_cg_preview_sets_error_status_for_empty_missing_or_unloadable_image(tmp_path):
    _app()
    window = ChatUIWindow()
    before_count = window.temporary_layout.count()

    assert window.add_cg_preview("") is False
    assert window.reply_status_label.text() == "CG 预览失败：图片路径为空"
    assert "rgba(173, 81, 74" in window.reply_status_label.styleSheet()

    missing_path = tmp_path / "missing.png"
    assert window.add_cg_preview(str(missing_path)) is False
    assert window.reply_status_label.text() == f"CG 预览失败：图片文件不存在：{missing_path}"
    assert "rgba(173, 81, 74" in window.reply_status_label.styleSheet()

    bad_path = tmp_path / "bad.png"
    bad_path.write_text("not an image", encoding="utf-8")
    assert window.add_cg_preview(str(bad_path)) is False
    assert window.reply_status_label.text() == f"CG 预览失败：图片无法加载：{bad_path}"
    assert "rgba(173, 81, 74" in window.reply_status_label.styleSheet()
    assert window.temporary_layout.count() == before_count


def test_clear_messages_resets_cg_preview_state(tmp_path):
    _app()
    image_path = tmp_path / "cg.png"
    image_path.write_bytes(_minimal_png_rgba(width=8, height=8))
    window = ChatUIWindow()
    window.add_message("hello", is_user=True)
    assert window.add_cg_preview(str(image_path)) is True
    assert window._cg_preview_labels
    assert window.last_cg_preview_path == str(image_path)
    assert window.temporary_layout.count() > 0

    window.clear_messages()

    assert window.temporary_layout.count() == 0
    assert window._cg_preview_labels == []
    assert window.last_cg_preview_path == ""


def test_open_cg_generated_dir_button_creates_dir_opens_local_path_and_sets_status(tmp_path, monkeypatch):
    _app()
    monkeypatch.chdir(tmp_path)
    generated_dir = tmp_path / "data" / "cg" / "generated"
    opened = []
    window = ChatUIWindow()
    window._open_local_path = lambda path: opened.append(path) or True

    window.open_cg_generated_dir_btn.click()

    assert generated_dir.is_dir()
    assert opened == [generated_dir]
    assert window.reply_status_label.text() == f"已打开 CG 生成目录：{generated_dir}"
    assert "rgba(35, 48, 57" in window.reply_status_label.styleSheet()


def test_open_cg_generated_dir_sets_error_status_when_open_fails(tmp_path, monkeypatch):
    _app()
    monkeypatch.chdir(tmp_path)
    generated_dir = tmp_path / "data" / "cg" / "generated"
    window = ChatUIWindow()
    window._open_local_path = lambda path: False

    assert window.open_cg_generated_dir() is False

    assert generated_dir.is_dir()
    assert window.reply_status_label.text() == f"打开 CG 生成目录失败：{generated_dir}"
    assert "rgba(173, 81, 74" in window.reply_status_label.styleSheet()


def test_open_cg_generated_dir_sets_error_status_when_directory_creation_fails(tmp_path, monkeypatch):
    _app()
    monkeypatch.chdir(tmp_path)
    opened = []
    window = ChatUIWindow()
    window._open_local_path = lambda path: opened.append(path) or True

    def fail_mkdir(self, parents=False, exist_ok=False):
        raise OSError("mkdir denied")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)

    assert window.open_cg_generated_dir() is False

    assert opened == []
    assert "打开 CG 生成目录失败" in window.reply_status_label.text()
    assert "rgba(173, 81, 74" in window.reply_status_label.styleSheet()


def test_chat_window_exposes_core_automation_anchors():
    _app()
    window = ChatUIWindow()

    def assert_anchor(widget, object_name: str, accessible_name: str):
        assert widget.objectName() == object_name
        assert widget.accessibleName() == accessible_name

    assert window.objectName() == "main_window"
    assert_anchor(window.close_btn, "close_button", "Close")
    assert_anchor(window.sprite_widget, "character_sprite_view", "Character sprite view")
    assert_anchor(
        window.temporary_content_scroll_area,
        "temporary_content_scroll_area",
        "Temporary conversation content",
    )
    assert_anchor(
        window.temporary_content_widget,
        "temporary_content_widget",
        "Temporary conversation content",
    )
    assert_anchor(window.session_title_label, "session_title_label", "Current session title")
    assert_anchor(window.rename_session_btn, "rename_session_button", "Rename current session")
    assert_anchor(window.archive_session_btn, "archive_session_button", "Archive current session")
    assert_anchor(window.reply_status_label, "reply_status_label", "Reply status")
    assert_anchor(window.tool_summary_frame, "tool_summary_frame", "Tool summary")
    assert_anchor(window.tool_summary_toggle_btn, "tool_summary_toggle_button", "Toggle tool summary")
    assert_anchor(window.input_edit, "chat_input", "Chat input")
    assert_anchor(window.reroll_btn, "reroll_button", "Reroll last message")
    assert_anchor(window.send_btn, "send_button", "Send message")
    assert_anchor(window.menu_btn, "action_menu_button", "More actions")
    assert_anchor(window.clear_btn, "clear_chat_button", "Clear chat")
    assert_anchor(window.open_cg_generated_dir_btn, "open_cg_generated_dir_button", "Open CG generated directory")
    assert_anchor(window.session_btn, "session_manager_button", "Session manager")
    assert_anchor(window.settings_btn, "settings_button", "Open settings")


def test_core_automation_anchors_support_minimal_click_flow():
    _app()
    window = ChatUIWindow()
    sent_messages = []
    settings_requests = []
    window.user_message_sent.connect(sent_messages.append)
    window.settings_requested.connect(lambda: settings_requests.append("settings"))

    chat_input = window.findChild(type(window.input_edit), "chat_input")
    send_button = window.findChild(type(window.send_btn), "send_button")
    settings_button = window.findChild(type(window.settings_btn), "settings_button")

    assert chat_input is window.input_edit
    assert send_button is window.send_btn
    assert settings_button is window.settings_btn

    chat_input.setText("锚点点击测试")
    send_button.click()
    settings_button.click()

    assert sent_messages == ["锚点点击测试"]
    assert chat_input.text() == ""
    assert settings_requests == ["settings"]
