from queue import Queue
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt

from core.runtime.chat_actions import (
    NO_RETRY_MESSAGE,
    handle_clear_requested,
    handle_new_session_requested,
    handle_reroll_requested,
    handle_session_skills_requested,
    handle_user_send,
)


class FakeWindow:
    def __init__(self):
        self.waiting = None
        self.statuses = []
        self.messages = []
        self.clear_messages_count = 0
        self.clear_reply_status_count = 0

    def set_waiting_for_reply(self, waiting):
        self.waiting = waiting

    def set_reply_status(self, text, error=False):
        self.statuses.append({"text": text, "error": error})

    def add_message(self, text, is_user=False, char_name="", char_color="#f2a0bd"):
        self.messages.append({
            "text": text,
            "is_user": is_user,
            "char_name": char_name,
            "char_color": char_color,
        })

    def clear_messages(self):
        self.clear_messages_count += 1
        self.messages.clear()

    def clear_reply_status(self):
        self.clear_reply_status_count += 1


class FakeHistory:
    def __init__(self, entries=None, last_user_content=None, pop_result=True):
        self.entries = list(entries or [])
        self.last_user_content = last_user_content
        self.pop_result = pop_result
        self.cleared = False
        self.added = []
        self.pop_called = False

    def add_to_history(self, role, content, **kwargs):
        self.added.append({"role": role, "content": content, **kwargs})
        self.entries.append({"role": role, "content": content, **kwargs})

    def clear_history(self):
        self.cleared = True
        self.entries.clear()

    def get_last_user_content(self):
        return self.last_user_content

    def pop_last_turn(self):
        self.pop_called = True
        if self.pop_result:
            # 模拟删除最后一轮后只剩早前历史。
            self.entries = [
                {"role": "user", "content": "第一句"},
                {"role": "assistant", "content": "第一句回复", "name": "诺艾尔"},
            ]
        return self.pop_result

    def get_history(self):
        return list(self.entries)


def test_handle_user_send_updates_window_history_and_queue():
    window = FakeWindow()
    history = FakeHistory()
    queue = Queue()

    handle_user_send(window, history, queue, "你好")

    assert window.waiting is True
    assert window.statuses == [{"text": "已发送，等待模型回复...", "error": False}]
    assert history.added == [{"role": "user", "content": "你好"}]
    assert queue.get_nowait() == "你好"


def test_handle_clear_requested_clears_history_and_window(monkeypatch):
    monkeypatch.setattr("core.runtime.chat_actions._confirm_clear", lambda window: True)
    window = FakeWindow()
    history = FakeHistory(entries=[{"role": "user", "content": "你好"}])

    handle_clear_requested(window, history)

    assert history.cleared is True
    assert window.clear_messages_count == 1
    assert window.clear_reply_status_count == 1
    assert window.statuses == [{"text": "对话历史已清空", "error": False}]


def test_handle_clear_requested_cancelled_does_nothing(monkeypatch):
    """用户在确认弹窗点'否'时，不执行清空。"""
    monkeypatch.setattr("core.runtime.chat_actions._confirm_clear", lambda window: False)
    window = FakeWindow()
    history = FakeHistory(entries=[{"role": "user", "content": "你好"}])

    handle_clear_requested(window, history)

    assert history.cleared is False
    assert window.clear_messages_count == 0
    assert window.clear_reply_status_count == 0
    assert window.statuses == []


def test_handle_reroll_requested_reports_error_without_retry_text():
    window = FakeWindow()
    history = FakeHistory(last_user_content=None)
    queue = Queue()

    handle_reroll_requested(window, history, queue, default_char_color="#ABCDEF")

    assert history.pop_called is False
    assert window.statuses == [{"text": NO_RETRY_MESSAGE, "error": True}]
    assert queue.empty()


def test_handle_reroll_requested_reports_error_when_pop_fails():
    window = FakeWindow()
    history = FakeHistory(last_user_content="第二句", pop_result=False)
    queue = Queue()

    handle_reroll_requested(window, history, queue, default_char_color="#ABCDEF")

    assert history.pop_called is True
    assert window.statuses == [{"text": NO_RETRY_MESSAGE, "error": True}]
    assert queue.empty()


def test_handle_reroll_requested_restores_history_and_requeues_last_user_text():
    window = FakeWindow()
    history = FakeHistory(last_user_content="第二句", pop_result=True)
    queue = Queue()

    handle_reroll_requested(window, history, queue, default_char_color="#ABCDEF")

    assert window.clear_messages_count == 1
    assert window.waiting is True
    assert window.statuses == [{"text": "正在重新生成上一轮回复...", "error": False}]
    assert window.messages == [
        {"text": "第一句", "is_user": True, "char_name": "", "char_color": "#ABCDEF"},
        {"text": "第一句回复", "is_user": False, "char_name": "诺艾尔", "char_color": "#ABCDEF"},
        {"text": "第二句", "is_user": True, "char_name": "", "char_color": "#f2a0bd"},
    ]
    assert history.added[-1] == {"role": "user", "content": "第二句"}
    assert queue.get_nowait() == "第二句"


def test_handle_new_session_requested_uses_global_default_skills_when_requested():
    window = FakeWindow()
    window.set_session_list = lambda sessions, active_id: None
    created = []

    history = SimpleNamespace(
        list_sessions=lambda include_archived=False: [],
        create_session=lambda title, character_name, make_active, enabled_skills=None: created.append(
            {
                "title": title,
                "character_name": character_name,
                "make_active": make_active,
                "enabled_skills": enabled_skills,
            }
        ) or SimpleNamespace(title=title),
        get_history=lambda: [],
        get_active_session_id=lambda: "session-1",
    )
    config = SimpleNamespace(
        default_skills=["shared", "global-a"],
        skill_presets=[SimpleNamespace(name="推理", skills=["mystery-a"])],
    )

    handle_new_session_requested(
        window,
        history,
        "#ABCDEF",
        character_name="诺艾尔",
        config=config,
        preset_name="全局默认",
    )

    assert created == [
        {
            "title": "新会话 1",
            "character_name": "诺艾尔",
            "make_active": True,
            "enabled_skills": ["shared", "global-a"],
        }
    ]


def test_handle_new_session_requested_uses_named_preset_skills_when_requested():
    window = FakeWindow()
    window.set_session_list = lambda sessions, active_id: None
    created = []

    history = SimpleNamespace(
        list_sessions=lambda include_archived=False: [],
        create_session=lambda title, character_name, make_active, enabled_skills=None: created.append(
            {
                "title": title,
                "character_name": character_name,
                "make_active": make_active,
                "enabled_skills": enabled_skills,
            }
        ) or SimpleNamespace(title=title),
        get_history=lambda: [],
        get_active_session_id=lambda: "session-1",
    )
    config = SimpleNamespace(
        default_skills=["shared", "global-a"],
        skill_presets=[SimpleNamespace(name="推理", skills=["mystery-a", "foreshadowing"])],
    )

    handle_new_session_requested(
        window,
        history,
        "#ABCDEF",
        character_name="诺艾尔",
        config=config,
        preset_name="推理",
    )

    assert created == [
        {
            "title": "新会话 1",
            "character_name": "诺艾尔",
            "make_active": True,
            "enabled_skills": ["mystery-a", "foreshadowing"],
        }
    ]


def test_handle_new_session_requested_copies_skills_so_existing_session_isolated_from_later_config_changes():
    window = FakeWindow()
    window.set_session_list = lambda sessions, active_id: None
    created = []

    def create_session(title, character_name, make_active, enabled_skills=None):
        record = {
            "title": title,
            "character_name": character_name,
            "make_active": make_active,
            "enabled_skills": enabled_skills,
        }
        created.append(record)
        return SimpleNamespace(title=title)

    history = SimpleNamespace(
        list_sessions=lambda include_archived=False: [],
        create_session=create_session,
        get_history=lambda: [],
        get_active_session_id=lambda: "session-1",
    )
    config = SimpleNamespace(
        default_skills=["shared", "global-a"],
        skill_presets=[SimpleNamespace(name="推理", skills=["mystery-a"])],
    )

    handle_new_session_requested(
        window,
        history,
        "#ABCDEF",
        character_name="诺艾尔",
        config=config,
        preset_name="全局默认",
    )
    config.default_skills.append("later-added")
    config.skill_presets[0].skills.append("later-preset-added")

    assert created == [
        {
            "title": "新会话 1",
            "character_name": "诺艾尔",
            "make_active": True,
            "enabled_skills": ["shared", "global-a"],
        }
    ]


def test_handle_session_skills_requested_shows_lightweight_name_description_list_and_saves_selection(monkeypatch):
    dialog_holder = {}

    class FakeDialog:
        def __init__(self, parent=None):
            self.parent = parent
            self.window_title = ""
            self.size = None
            self.accepted = False
            self.rejected = False
            dialog_holder["dialog"] = self

        def setWindowTitle(self, title):
            self.window_title = title

        def resize(self, width, height):
            self.size = (width, height)

        def accept(self):
            self.accepted = True

        def reject(self):
            self.rejected = True

        def exec(self):
            save_button = dialog_holder["save_button"]
            save_button.clicked._callback()
            return 0

    class FakeLayout:
        def __init__(self, parent=None):
            self.parent = parent
            self.widgets = []

        def addWidget(self, widget):
            self.widgets.append(widget)

    class FakeSignal:
        def __init__(self):
            self._callback = None

        def connect(self, callback):
            self._callback = callback

    class FakeButton:
        def __init__(self, text):
            self.text = text
            self.clicked = FakeSignal()
            if text == "保存":
                dialog_holder["save_button"] = self

        def setObjectName(self, name):
            self.object_name = name

    class FakeListWidgetItem:
        def __init__(self, text):
            self._text = text
            self._data = {}
            self._flags = Qt.ItemFlag.NoItemFlags
            self._check_state = Qt.CheckState.Unchecked

        def text(self):
            return self._text

        def setData(self, role, value):
            self._data[role] = value

        def data(self, role):
            return self._data.get(role)

        def flags(self):
            return self._flags

        def setFlags(self, flags):
            self._flags = flags

        def setCheckState(self, state):
            self._check_state = state

        def checkState(self):
            return self._check_state

    class FakeListWidget:
        def __init__(self, parent=None):
            self.parent = parent
            self.items = []
            dialog_holder["list_widget"] = self

        def addItem(self, item):
            self.items.append(item)

        def count(self):
            return len(self.items)

        def item(self, row):
            return self.items[row]

    import core.runtime.chat_actions as chat_actions

    monkeypatch.setattr(chat_actions, "QDialog", FakeDialog)
    monkeypatch.setattr(chat_actions, "QPushButton", FakeButton)
    monkeypatch.setattr(chat_actions, "QListWidget", FakeListWidget)
    monkeypatch.setattr(chat_actions, "QListWidgetItem", FakeListWidgetItem)
    monkeypatch.setattr(chat_actions, "build_frameless_dialog_shell", lambda dialog, title, **kwargs: FakeLayout(dialog))

    window = FakeWindow()
    synced = []
    window.set_session_list = lambda sessions, active_id: synced.append((sessions, active_id))

    updated = []
    session = SimpleNamespace(id="session-1", title="会话一", enabled_skills=["skill-a"], archived=False, updated_at="now")
    history = SimpleNamespace(
        get_session_store=lambda: SimpleNamespace(get_session=lambda session_id: session if session_id == "session-1" else None),
        update_session_enabled_skills=lambda session_id, selected: updated.append((session_id, selected)),
        list_sessions=lambda include_archived=True: [session],
        get_active_session_id=lambda: "session-1",
    )
    config = SimpleNamespace(skills_root="/tmp/skills")

    repository = SimpleNamespace(
        list_skills=lambda: [
            SimpleNamespace(name="skill-a", description="Alpha desc"),
            SimpleNamespace(name="skill-b", description="Beta desc"),
        ]
    )
    monkeypatch.setattr(chat_actions, "SkillRepository", lambda roots: repository)

    handle_session_skills_requested(window, history, config, "session-1")

    list_widget = dialog_holder["list_widget"]
    assert [item.text() for item in list_widget.items] == [
        "skill-a — Alpha desc",
        "skill-b — Beta desc",
    ]
    assert updated == [("session-1", ["skill-a"])]
    assert window.statuses[-1] == {"text": "已更新会话技能：会话一", "error": False}
    assert dialog_holder["dialog"].accepted is True
