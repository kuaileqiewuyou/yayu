"""Choice suggestions remain optional and never prevent a user's own reply."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton
from shiboken6 import isValid

from ui import motion
from ui.chat_ui.chat_ui import ChatUIWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app):
    reduced = motion.reduced_motion()
    motion.set_reduced_motion(True)
    chat = ChatUIWindow()
    chat.resize(960, 760)
    chat.show()
    app.processEvents()
    yield chat
    chat.close()
    chat.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    motion.set_reduced_motion(reduced)


def _choices(window, app, options=None):
    window.post_options(options if options is not None else ["去公园", "留在这里", "聊聊别的"])
    app.processEvents()
    group = window._choice_group
    assert group is not None
    return group, group.findChildren(QPushButton, "choice_button")


def _sent_messages(window):
    sent = []
    window.user_message_sent.connect(sent.append)
    return sent


def test_choice_header_provides_small_actions_without_extra_choice_rows(window, app):
    group, buttons = _choices(window, app)
    custom = group.findChild(QPushButton, "choice_custom_reply_button")
    skip = group.findChild(QPushButton, "choice_skip_button")

    assert [button.text() for button in buttons] == ["1.  去公园", "2.  留在这里", "3.  聊聊别的"]
    assert custom is not None and custom.text() == "自定义回复"
    assert skip is not None and skip.text() == "跳过"
    assert custom.mapTo(group, custom.rect().topLeft()).y() < buttons[0].mapTo(group, buttons[0].rect().topLeft()).y()
    assert skip.mapTo(group, skip.rect().topLeft()).y() < buttons[0].mapTo(group, buttons[0].rect().topLeft()).y()
    assert skip.mapTo(group, skip.rect().center()).x() > group.width() * 0.75
    assert skip.width() < 100


@pytest.mark.parametrize("other_content", ["none", "card", "cg", "both"])
def test_skip_only_dismisses_choices_and_preserves_draft_dialogue_and_other_content(window, app, tmp_path, other_content):
    window.add_message("你想去哪里？", char_name="诺艾尔")
    remaining = []
    if other_content in {"card", "both"}:
        remaining.append(window.add_card("# 地点\n公园在附近。", title="地点资料"))
    if other_content in {"cg", "both"}:
        path = tmp_path / "CG.png"
        image = QImage(20, 20, QImage.Format.Format_RGB32)
        image.fill(QColor("#718874"))
        assert image.save(str(path))
        assert window.add_cg_preview(str(path))
        remaining.append(window.temporary_layout.itemAt(window.temporary_layout.count() - 1).widget())
    window.input_edit.setText("我想先问一件事")
    group, _ = _choices(window, app)
    history = window.message_history_snapshot()
    dialogue = window.current_message_label.text()
    sent = _sent_messages(window)

    QTest.mouseClick(group.findChild(QPushButton, "choice_skip_button"), Qt.MouseButton.LeftButton)

    assert window._choice_group is None
    assert group.isHidden()
    assert window.input_edit.text() == "我想先问一件事"
    assert window.message_history_snapshot() == history
    assert window.current_message_label.text() == dialogue
    assert sent == []
    assert window.scroll_area.isHidden() is (not remaining)
    for content in remaining:
        assert window.temporary_layout.indexOf(content) >= 0
        assert not content.isHidden()


def test_custom_reply_preserves_draft_and_focuses_input_without_sending(window, app):
    window.add_message("我们接下来做什么？", char_name="诺艾尔")
    window.input_edit.setText("我的打算是")
    group, _ = _choices(window, app)
    sent = _sent_messages(window)
    history = window.message_history_snapshot()

    QTest.mouseClick(group.findChild(QPushButton, "choice_custom_reply_button"), Qt.MouseButton.LeftButton)
    app.processEvents()

    assert window._choice_group is None
    assert group.isHidden()
    assert window.input_edit.text() == "我的打算是"
    assert window.input_edit.hasFocus()
    assert sent == []
    assert window.message_history_snapshot() == history


def test_manual_reply_removes_choices_and_sends_only_the_user_text(window, app):
    group, _ = _choices(window, app)
    window.input_edit.setText("  我想去图书馆  ")
    sent = _sent_messages(window)

    window._on_send()

    assert window._choice_group is None
    assert group.isHidden()
    assert window.input_edit.text() == ""
    assert sent == ["我想去图书馆"]
    assert window.message_history_snapshot()[-1]["text"] == "我想去图书馆"


@pytest.mark.parametrize("draft", ["", " \t "])
def test_empty_manual_send_keeps_the_choices(window, app, draft):
    group, _ = _choices(window, app)
    window.input_edit.setText(draft)
    sent = _sent_messages(window)

    window._on_send()

    assert window._choice_group is group
    assert not group.isHidden()
    assert window.input_edit.text() == draft
    assert sent == []


def test_manual_send_while_waiting_keeps_choices_and_draft(window, app):
    group, _ = _choices(window, app)
    window.input_edit.setText("等我说完")
    window.set_waiting_for_reply(True)
    sent = _sent_messages(window)
    history = window.message_history_snapshot()

    window._on_send()

    assert window._choice_group is group
    assert not group.isHidden()
    assert window.input_edit.text() == "等我说完"
    assert window.message_history_snapshot() == history
    assert sent == []


def test_selecting_a_suggestion_dismisses_it_and_sends_once(window, app):
    group, buttons = _choices(window, app)
    sent = _sent_messages(window)

    buttons[1].click()
    buttons[1].click()

    assert sent == ["留在这里"]
    assert window._choice_group is None
    assert group.isHidden()
    assert [entry["text"] for entry in window.message_history_snapshot()] == ["留在这里"]


def test_choices_arriving_during_reply_are_blocked_until_reply_finishes(window, app):
    window.set_waiting_for_reply(True)
    group, buttons = _choices(window, app)
    sent = _sent_messages(window)
    assert all(not button.isEnabled() for button in buttons)

    buttons[0].click()
    window._on_option_clicked("去公园", group)
    assert sent == []
    assert window._choice_group is group

    window.set_waiting_for_reply(False)
    assert all(button.isEnabled() for button in buttons)
    buttons[0].click()
    assert sent == ["去公园"]
    assert window._choice_group is None


def test_existing_choices_follow_waiting_state_without_losing_the_group(window, app):
    group, buttons = _choices(window, app)

    window.set_waiting_for_reply(True)
    assert window._choice_group is group
    assert all(not button.isEnabled() for button in buttons)

    window.set_waiting_for_reply(False)
    assert window._choice_group is group
    assert all(button.isEnabled() for button in buttons)


def test_skip_during_reply_does_not_cancel_or_send_a_turn(window, app):
    window.set_waiting_for_reply(True)
    group, _ = _choices(window, app)
    window.input_edit.setText("保留的草稿")
    sent = _sent_messages(window)

    group.findChild(QPushButton, "choice_skip_button").click()

    assert window._choice_group is None
    assert window._waiting_for_reply is True
    assert not window.input_edit.isEnabled()
    assert window.input_edit.text() == "保留的草稿"
    assert sent == []


def test_custom_reply_while_waiting_preserves_draft_and_defers_focus(window, app):
    window.input_edit.setText("我自己回答")
    window.set_waiting_for_reply(True)
    group, _ = _choices(window, app)
    sent = _sent_messages(window)

    QTest.mouseClick(group.findChild(QPushButton, "choice_custom_reply_button"), Qt.MouseButton.LeftButton)
    assert window._choice_group is None
    assert window.input_edit.text() == "我自己回答"
    assert not window.input_edit.isEnabled()
    assert sent == []

    window.set_waiting_for_reply(False)
    app.processEvents()
    assert window.input_edit.hasFocus()
    assert window.input_edit.text() == "我自己回答"
    assert sent == []


def test_new_options_replace_old_group_and_stale_click_cannot_send(window, app):
    old_group, old_buttons = _choices(window, app)
    window.post_options(["新的建议"])
    new_group = window._choice_group
    new_buttons = new_group.findChildren(QPushButton, "choice_button")
    sent = _sent_messages(window)

    assert old_group.isHidden()
    assert window.temporary_layout.indexOf(old_group) == -1
    assert window._choice_group is new_group
    # A click already queued for the removed group must not submit an old answer.
    old_buttons[0].clicked[bool].emit(False)
    window._on_option_clicked("去公园", old_group)
    assert sent == []
    assert window._choice_group is new_group

    new_buttons[0].click()
    assert sent == ["新的建议"]


@pytest.mark.parametrize("options", [[], ["", "  ", None]])
def test_empty_options_remove_previous_choices_without_an_empty_panel(window, app, options):
    old_group, _ = _choices(window, app)
    sent = _sent_messages(window)

    window.post_options(options)

    assert window._choice_group is None
    assert old_group.isHidden()
    assert window.scroll_area.isHidden()
    assert sent == []


def test_session_clear_invalidates_previous_choice_callbacks(window, app):
    group, buttons = _choices(window, app)
    sent = _sent_messages(window)

    window.clear_messages()
    buttons[0].clicked[bool].emit(False)
    window._on_option_clicked("去公园", group)

    assert window._choice_group is None
    assert window.scroll_area.isHidden()
    assert window.message_history_snapshot() == []
    assert sent == []


def test_skip_during_normal_entrance_stops_animation_before_deleting_group(window, app, monkeypatch):
    callback_errors = []
    monkeypatch.setattr(sys, "excepthook", lambda _kind, error, _traceback: callback_errors.append(error))
    motion.set_reduced_motion(False)
    try:
        window.post_options(["去公园", "留在这里"])
        group = window._choice_group
        assert group._entrance_group is not None
        sent = _sent_messages(window)

        group.findChild(QPushButton, "choice_skip_button").click()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert not isValid(group)
        # Advancing beyond completion exposes animations that retain a deleted frame.
        QTest.qWait(motion.SLOW + 70)

        assert callback_errors == []
        assert window._choice_group is None
        assert window.scroll_area.isHidden()
        assert sent == []
    finally:
        motion.set_reduced_motion(True)
