"""台词框：逐字显示、点击补全、▼ 续读提示、思考中跳点。"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ui import motion
from ui.chat_ui.dialogue_text import DialogueTextLabel


class FixedClock:
    def __init__(self, now=10_000):
        self.now = now

    def elapsed(self):
        return self.now


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def restore_motion():
    yield
    motion.set_reduced_motion(False)
    motion.set_typewriter(True, motion.TYPEWRITER_CPS)


def make_label(clock):
    label = DialogueTextLabel()
    label.resize(400, 80)
    label._clock = clock
    return label


def test_reveal_shows_prefix_over_time_while_text_returns_full_line(app):
    clock = FixedClock()
    label = make_label(clock)

    label.reveal("你好，欢迎回来。")

    assert label.text() == "你好，欢迎回来。"
    assert label.is_revealing()
    assert label.visible_text() == ""
    clock.now += motion.typewriter_duration_ms(8) // 2
    assert label.visible_text() == "你好，欢迎"[:4]
    clock.now += motion.typewriter_duration_ms(8)
    assert label.visible_text() == "你好，欢迎回来。"


def test_reveal_duration_is_capped_for_long_lines(app):
    assert motion.typewriter_duration_ms(10_000) == motion.TYPEWRITER_MAX_MS


def test_click_completes_reveal_and_shows_continue_indicator(app):
    clock = FixedClock()
    label = make_label(clock)
    finished = []
    label.reveal_finished.connect(lambda: finished.append(True))
    label.reveal("一句很长的台词")
    assert not label.indicator_visible()

    QTest.mouseClick(label, Qt.MouseButton.LeftButton)

    assert not label.is_revealing()
    assert label.visible_text() == "一句很长的台词"
    assert label.indicator_visible()
    assert finished == [True]


def test_frame_after_duration_finishes_reveal(app):
    clock = FixedClock()
    label = make_label(clock)
    label.reveal("短句")

    clock.now += motion.typewriter_duration_ms(2) + 1
    label._on_frame()

    assert not label.is_revealing()
    assert label.indicator_visible()


def test_set_text_is_immediate_without_indicator(app):
    label = make_label(FixedClock())

    label.setText("用户输入")

    assert not label.is_revealing()
    assert label.visible_text() == "用户输入"
    assert not label.indicator_visible()


@pytest.mark.parametrize("configure", [
    lambda: motion.set_reduced_motion(True),
    lambda: motion.set_typewriter(False),
])
def test_reveal_is_instant_when_typewriter_off_or_reduced_motion(app, configure):
    configure()
    label = make_label(FixedClock())

    label.reveal("马上显示")

    assert not label.is_revealing()
    assert label.visible_text() == "马上显示"
    assert label.indicator_visible()


def test_thinking_dots_cycle_and_hide_indicator(app):
    clock = FixedClock(0)
    label = make_label(clock)
    label.reveal("上一句")
    label.complete_reveal()

    label.setText("")
    label.set_thinking(True)

    counts = []
    for _ in range(4):
        counts.append(label.thinking_dot_count())
        clock.now += motion.THINKING_DOT_INTERVAL
    assert counts == [1, 2, 3, 1]
    assert not label.indicator_visible()

    label.set_thinking(False)
    assert not label.is_thinking()


def test_reduced_motion_freezes_thinking_dots_and_indicator(app):
    motion.set_reduced_motion(True)
    label = make_label(FixedClock(0))

    assert label.thinking_dot_count(123) == 3
    assert label.indicator_offset(456) == 0.0


# ── 窗口集成 ─────────────────────────────────────────

@pytest.fixture
def window(app):
    from ui.chat_ui.chat_ui import ChatUIWindow

    w = ChatUIWindow()
    w.set_active_character_name("诺艾尔")
    yield w
    w.close()


def test_character_line_reveals_but_user_and_system_lines_do_not(window):
    label = window.current_message_label

    window.add_message("我的问题", is_user=True)
    assert not label.is_revealing()
    window.add_message("系统提示", char_name="系统")
    assert not label.is_revealing()

    window.add_message("角色回答", char_name="诺艾尔")
    assert label.is_revealing()
    assert label.text() == "角色回答"


def test_waiting_after_user_line_shows_thinking_with_character_name(window):
    window.add_message("在吗？", is_user=True)

    window.set_waiting_for_reply(True)

    assert window.current_message_label.is_thinking()
    assert window.current_speaker_label.text() == "诺艾尔"
    assert window.current_message_label.text() == ""
    assert window.message_history_snapshot()[-1]["text"] == "在吗？"


def test_empty_stream_placeholder_keeps_thinking_until_text_arrives(window):
    window.add_message("在吗？", is_user=True)
    window.set_waiting_for_reply(True)

    window.begin_stream(char_name="诺艾尔")
    assert window.current_message_label.is_thinking()

    window.append_stream("在")
    assert not window.current_message_label.is_thinking()


def test_first_parsed_line_and_reply_end_clear_thinking(window):
    window.add_message("在吗？", is_user=True)
    window.set_waiting_for_reply(True)
    window.begin_stream(char_name="诺艾尔")

    window.discard_stream()
    window.add_message("在的哦", char_name="诺艾尔")
    window.set_waiting_for_reply(False)

    assert not window.current_message_label.is_thinking()
    assert window.current_message_label.text() == "在的哦"


def test_cancelled_reply_restores_last_user_line(window):
    window.add_message("在吗？", is_user=True)
    window.set_waiting_for_reply(True)

    window.discard_stream()
    window.set_waiting_for_reply(False)

    assert not window.current_message_label.is_thinking()
    assert window.current_message_label.text() == "在吗？"
    assert window.current_speaker_label.text() == "你"


def test_dialogue_label_does_not_interpret_html(window):
    window.add_message("<b>粗体</b>", char_name="诺艾尔")

    assert window.current_message_label.textFormat() == Qt.TextFormat.PlainText


# ── 临时内容进入动效 ─────────────────────────────────

def test_card_entrance_starts_transparent_and_settles_without_effect(window):
    from ui.chat_ui.info_card import InfoCardWidget

    resting_top = InfoCardWidget("x", open_url=lambda u: None, copy_text=lambda t: None).contentsMargins().top()
    card = window.add_card("## 标题\n- 要点")

    assert card.graphicsEffect() is not None
    assert card.graphicsEffect().opacity() == pytest.approx(0.0)
    assert card.contentsMargins().top() == resting_top + motion.ENTRANCE_SLIDE_PX  # 上滑起点

    QTest.qWait(motion.SLOW + 150)

    assert card.graphicsEffect() is None  # 动画结束即移除透明度效果
    assert card.contentsMargins().top() == resting_top


def test_entrance_is_skipped_with_reduced_motion(window):
    from ui.chat_ui.info_card import InfoCardWidget

    resting_top = InfoCardWidget("x", open_url=lambda u: None, copy_text=lambda t: None).contentsMargins().top()
    motion.set_reduced_motion(True)

    card = window.add_card("## 标题")
    window.post_options(["好", "不好"])

    assert card.graphicsEffect() is None
    assert card.contentsMargins().top() == resting_top
