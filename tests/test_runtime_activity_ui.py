import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from ui.chat_ui.chat_ui import ChatUIWindow


def _app():
    return QApplication.instance() or QApplication([])


def test_waiting_turn_builds_runtime_timeline_and_finishes_cleanly():
    _app()
    window = ChatUIWindow()

    window.set_waiting_for_reply(True)
    window.set_reply_status("模型思考中...")
    window.set_reply_status("正在联网搜索：本周新闻")
    window.set_reply_status("联网搜索 完成")
    window.set_reply_status("")
    window.set_waiting_for_reply(False)

    assert window.runtime_state_badge_label.text() == "已完成"
    assert window.reply_status_label.text() == "本轮处理完成"
    assert [entry["text"] for entry in window._runtime_activity_entries] == [
        "请求已进入执行队列",
        "模型思考中...",
        "正在联网搜索：本周新闻",
        "联网搜索 完成",
        "本轮处理完成",
    ]


def test_runtime_timeline_deduplicates_bounds_and_escapes_event_text():
    app = _app()
    window = ChatUIWindow()
    window.set_waiting_for_reply(True)
    window.set_reply_status("重复事件")
    window.set_reply_status("重复事件")
    for index in range(15):
        window.set_reply_status(f"阶段 {index}")
    window.set_reply_status("<b>不应作为富文本执行</b>")
    app.processEvents()

    assert len(window._runtime_activity_entries) == 12
    rendered_rows = window.runtime_activity_widget.findChildren(QLabel, "runtime_activity_entry")
    assert rendered_rows
    assert "&lt;b&gt;" in rendered_rows[-1].text()


def test_failed_runtime_stays_failed_when_input_is_reenabled():
    _app()
    window = ChatUIWindow()
    window.set_waiting_for_reply(True)
    window.set_reply_status("回复失败：连接中断", error=True)
    window.set_waiting_for_reply(False)

    assert window.runtime_state_badge_label.text() == "失败"
    assert window._runtime_activity_entries[-1]["text"] == "回复失败：连接中断"
