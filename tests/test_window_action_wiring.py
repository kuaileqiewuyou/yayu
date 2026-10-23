from core.runtime.window_action_wiring import open_settings_window, wire_window_actions


class FakeSignal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)


class FakeWindow:
    def __init__(self):
        self.user_message_sent = FakeSignal()
        self.clear_requested = FakeSignal()
        self.reroll_requested = FakeSignal()
        self.settings_requested = FakeSignal()
        self.new_session_requested = FakeSignal()


class FakeSettingsWindow:
    def __init__(self):
        self.calls = []

    def show(self):
        self.calls.append("show")

    def raise_(self):
        self.calls.append("raise_")

    def activateWindow(self):
        self.calls.append("activateWindow")


def test_wire_window_actions_connects_user_clear_and_reroll_to_chat_action_handlers(monkeypatch):
    import core.runtime.window_action_wiring as window_action_wiring

    window = FakeWindow()
    history = object()
    queue = object()
    calls = []

    def fake_handle_user_send(created_window, created_history, created_queue, text):
        calls.append(("send", created_window, created_history, created_queue, text))

    def fake_handle_clear_requested(created_window, created_history):
        calls.append(("clear", created_window, created_history))

    def fake_handle_reroll_requested(
        created_window,
        created_history,
        created_queue,
        default_char_color,
    ):
        calls.append(("reroll", created_window, created_history, created_queue, default_char_color))

    monkeypatch.setattr(window_action_wiring, "handle_user_send", fake_handle_user_send)
    monkeypatch.setattr(window_action_wiring, "handle_clear_requested", fake_handle_clear_requested)
    monkeypatch.setattr(window_action_wiring, "handle_reroll_requested", fake_handle_reroll_requested)

    wire_window_actions(
        window=window,
        chat_history=history,
        user_input_queue=queue,
        default_char_color="#ABCDEF",
    )

    assert len(window.user_message_sent.slots) == 1
    assert len(window.clear_requested.slots) == 1
    assert len(window.reroll_requested.slots) == 1

    window.user_message_sent.slots[0]("你好")
    window.clear_requested.slots[0]()
    window.reroll_requested.slots[0]()

    assert calls == [
        ("send", window, history, queue, "你好"),
        ("clear", window, history),
        ("reroll", window, history, queue, "#ABCDEF"),
    ]


def test_open_settings_window_shows_raises_and_activates_settings_window():
    settings_window = FakeSettingsWindow()

    open_settings_window(settings_window)

    assert settings_window.calls == ["show", "raise_", "activateWindow"]


def test_wire_window_actions_connects_settings_when_settings_window_is_provided():
    window = FakeWindow()
    settings_window = FakeSettingsWindow()

    wire_window_actions(
        window=window,
        chat_history=object(),
        user_input_queue=object(),
        default_char_color="#ABCDEF",
        settings_window=settings_window,
    )

    assert len(window.settings_requested.slots) == 1

    window.settings_requested.slots[0]()

    assert settings_window.calls == ["show", "raise_", "activateWindow"]


def test_wire_window_actions_passes_preset_name_to_new_session_handler(monkeypatch):
    import core.runtime.window_action_wiring as window_action_wiring

    window = FakeWindow()
    history = object()
    queue = object()
    calls = []

    monkeypatch.setattr(window_action_wiring, "handle_user_send", lambda *args, **kwargs: None)
    monkeypatch.setattr(window_action_wiring, "handle_clear_requested", lambda *args, **kwargs: None)
    monkeypatch.setattr(window_action_wiring, "handle_reroll_requested", lambda *args, **kwargs: None)

    def fake_handle_new_session_requested(created_window, created_history, default_char_color, *, character_name, config=None, preset_name=None):
        calls.append((created_window, created_history, default_char_color, character_name, config, preset_name))

    monkeypatch.setattr(window_action_wiring, "handle_new_session_requested", fake_handle_new_session_requested)

    wire_window_actions(
        window=window,
        chat_history=history,
        user_input_queue=queue,
        default_char_color="#ABCDEF",
        active_character_name="诺艾尔",
        config={"skills": True},
    )

    assert len(window.new_session_requested.slots) == 1
    window.new_session_requested.slots[0]("全局默认")

    assert calls == [(window, history, "#ABCDEF", "诺艾尔", {"skills": True}, "全局默认")]


def test_wire_window_actions_does_not_connect_settings_when_settings_window_is_none():
    window = FakeWindow()

    wire_window_actions(
        window=window,
        chat_history=object(),
        user_input_queue=object(),
        default_char_color="#ABCDEF",
        settings_window=None,
    )

    assert window.settings_requested.slots == []
