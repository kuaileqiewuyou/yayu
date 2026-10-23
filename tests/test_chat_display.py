from core.runtime.chat_display import restore_chat_history_to_window


class FakeWindow:
    def __init__(self):
        self.messages = []

    def add_message(self, text, is_user=False, char_name="", char_color="#f2a0bd"):
        self.messages.append({
            "text": text,
            "is_user": is_user,
            "char_name": char_name,
            "char_color": char_color,
        })


def test_restore_chat_history_to_window_displays_user_and_assistant_entries():
    window = FakeWindow()
    entries = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "我在哦", "name": "诺艾尔"},
    ]

    restore_chat_history_to_window(window, entries, default_char_color="#ABCDEF")

    assert window.messages == [
        {"text": "你好", "is_user": True, "char_name": "", "char_color": "#ABCDEF"},
        {"text": "我在哦", "is_user": False, "char_name": "诺艾尔", "char_color": "#ABCDEF"},
    ]


def test_restore_chat_history_to_window_displays_system_entries():
    window = FakeWindow()
    entries = [
        {"role": "system", "content": "已切换场景", "name": "系统", "color": "#84C2D5"},
    ]

    restore_chat_history_to_window(window, entries, default_char_color="#ABCDEF")

    assert window.messages == [
        {"text": "已切换场景", "is_user": False, "char_name": "系统", "char_color": "#84C2D5"},
    ]
