from core.runtime.llm_ui_handlers import LLMUiHandlers
from sdk.messages import LLMDialogMessage
from ui.chat_ui.chat_ui import ChatUIWindow


class FakeWindow:
    def __init__(self):
        self.begin_stream_calls = []
        self.end_stream_count = 0
        self.waiting = None
        self.messages = []
        self.discard_stream_count = 0

    def begin_stream(self, char_name="", char_color="#f2a0bd"):
        self.begin_stream_calls.append({"char_name": char_name, "char_color": char_color})

    def end_stream(self):
        self.end_stream_count += 1

    def discard_stream(self):
        self.discard_stream_count += 1

    def set_waiting_for_reply(self, waiting):
        self.waiting = waiting

    def add_message(self, text, is_user=False, char_name="", char_color="#f2a0bd"):
        self.messages.append({
            "text": text,
            "is_user": is_user,
            "char_name": char_name,
            "char_color": char_color,
        })


class FakeHistory:
    def __init__(self):
        self.added = []
        self.save_count = 0

    def add_to_history(self, role, content, **kwargs):
        self.added.append({"role": role, "content": content, **kwargs})

    def save(self):
        self.save_count += 1


def make_handlers(window=None, history=None, sprite_calls=None):
    window = window or FakeWindow()
    history = history or FakeHistory()
    sprite_calls = sprite_calls if sprite_calls is not None else []
    return LLMUiHandlers(
        window=window,
        history=history,
        active_character_name="诺艾尔",
        char_color="#ABCDEF",
        set_sprite_by_id=sprite_calls.append,
    ), window, history, sprite_calls


def test_on_stream_start_begins_stream_with_active_character():
    handlers, window, _, _ = make_handlers()

    handlers.on_stream_start()

    assert window.begin_stream_calls == [{"char_name": "诺艾尔", "char_color": "#ABCDEF"}]


def test_on_dialog_parsed_displays_dialog_updates_sprite_and_history():
    handlers, window, history, sprite_calls = make_handlers()
    msg = LLMDialogMessage(name="诺艾尔", text="欢迎回来。", asset_id="2")

    handlers.on_dialog_parsed(msg)

    assert window.discard_stream_count == 1
    assert window.end_stream_count == 0
    assert window.messages == [
        {"text": "欢迎回来。", "is_user": False, "char_name": "诺艾尔", "char_color": "#ABCDEF"},
    ]
    assert sprite_calls == ["2"]
    assert history.added == [
        {"role": "assistant", "content": "欢迎回来。", "name": "诺艾尔", "asset_id": "2"},
    ]


def test_on_dialog_parsed_ignores_non_displayed_control_tokens():
    handlers, window, history, sprite_calls = make_handlers()
    msg = LLMDialogMessage(name="CHOICE", text="继续 / 离开", asset_id="-1")

    handlers.on_dialog_parsed(msg)

    assert window.end_stream_count == 0
    assert window.messages == []
    assert sprite_calls == []
    assert history.added == []


def test_on_stream_end_ends_stream_clears_waiting_and_saves_history():
    handlers, window, history, _ = make_handlers()

    handlers.on_stream_end()

    assert window.end_stream_count == 1
    assert window.waiting is False
    assert history.save_count == 1


def test_on_llm_error_displays_error_and_clears_waiting():
    handlers, window, history, _ = make_handlers()

    handlers.on_llm_error("网络失败")

    assert window.end_stream_count == 1
    assert window.waiting is False
    assert history.save_count == 0
    assert window.messages == [
        {"text": "[错误] 网络失败", "is_user": False, "char_name": "系统", "char_color": "#FF4444"},
    ]


def test_real_window_stream_parse_end_keeps_only_formal_dialogue(qtbot):
    window = ChatUIWindow()
    qtbot.addWidget(window)
    handlers, _, history, _ = make_handlers(window=window)

    handlers.on_stream_start()
    window.append_stream('{"character_name":"诺艾尔","speech":"协议原文"}')
    handlers.on_dialog_parsed(LLMDialogMessage(name="诺艾尔", text="正式对白", asset_id="2"))
    handlers.on_stream_end()

    assert window.message_history_snapshot() == [
        {"text": "正式对白", "is_user": False, "char_name": "诺艾尔", "char_color": "#ABCDEF"},
    ]
    assert history.added == [
        {"role": "assistant", "content": "正式对白", "name": "诺艾尔", "asset_id": "2"},
    ]
