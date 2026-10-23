from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog, QPlainTextEdit, QLabel

from config.schema import Character
from core.sessions.store import SessionStore
from ui.settings_ui.memory_tab import MemoryTab


@pytest.fixture
def tab(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    sessions = SessionStore(history_root=tmp_path, sessions_dir=tmp_path / "sessions", index_path=tmp_path / "sessions.json")
    character = Character(name="爱丽丝")
    session = sessions.create_session(title="测试存档", character_name=character.name)
    sessions.memory.ensure_session(session.id, character.memory_id)
    history = SimpleNamespace(get_memory_store=lambda: sessions.memory, get_session_store=lambda: sessions,
                              list_sessions=sessions.list_sessions, get_active_session_id=lambda: session.id)
    widget = MemoryTab(SimpleNamespace(characters=[character]), history=history)
    widget.refresh_sessions()
    yield widget
    widget.dirty = False
    widget._options_dirty = False
    widget.close()
    widget.deleteLater()
    app.processEvents()


def test_memory_editor_save_pin_scope_and_confirmation(tab):
    tab.content.setPlainText("请叫我小林")
    tab.pinned.setChecked(True)
    tab.scope.setCurrentIndex(tab.scope.findData("global"))
    tab.save_memory()
    memories = tab.store.list_memories(tab.session_id())
    assert len(memories) == 1
    assert memories[0]["scope"] == "global" and memories[0]["pinned"]
    assert memories[0]["certainty"] == "explicit"
    tab.content.setPlainText("请叫我林林")
    tab.save_memory()
    assert [m["content"] for m in tab.store.list_memories(tab.session_id())] == ["请叫我林林"]


def test_empty_memory_save_and_running_job_actions(tab):
    tab.new_memory()
    assert not tab.save_button.isEnabled()
    tab.content.setPlainText("新的记忆")
    assert tab.save_button.isEnabled()
    state = tab.store.session(tab.session_id())
    tab.store.set_status(tab.session_id(), state["revision"], "running")
    tab.refresh_status()
    assert not tab.tool_buttons["立即整理 / 重试"].isEnabled()
    assert not tab.tool_buttons["重新构建"].isEnabled()
    assert tab.content.isEnabled()
    tab.store.set_status(tab.session_id(), state["revision"], "failed", "示例连接错误")
    tab.refresh_status()
    assert tab.tool_buttons["立即整理 / 重试"].isEnabled()
    assert tab.tool_buttons["重新构建"].isEnabled()
    assert tab.progress.property("state") == "failed"


def test_cancel_memory_delete_keeps_record_and_draft(tab, monkeypatch):
    tab.content.setPlainText("已有记忆")
    tab.save_memory()
    tab.content.setPlainText("仍在修改的草稿")
    monkeypatch.setattr("ui.settings_ui.memory_tab.confirm", lambda *args, **kwargs: False)
    tab.delete_memory()
    assert tab.content.toPlainText() == "仍在修改的草稿" and tab.dirty
    assert tab.store.list_memories(tab.session_id())[0]["content"] == "已有记忆"


def test_memory_editor_shows_sources_and_filters_types(tab):
    store = tab.store
    store.sync_messages(tab.session_id(), [{"role": "user", "content": "我喜欢咖啡"}, {"role": "assistant", "content": "记住啦"}])
    source = store.turns(tab.session_id())[0]["id"]
    store.edit(tab.session_id(), {"type": "preference", "content": "喜欢咖啡", "source_turn_ids": [source], "certainty": "explicit"})
    tab.refresh()
    assert "我喜欢咖啡" in tab.source_text.toPlainText()
    tab.types.setCurrentIndex(tab.types.findData("event"))
    assert tab.list.count() == 0


def test_memory_inheritance_controls_are_explicit_and_persist(tab):
    assert not tab.inherit.isChecked() and not tab.global_memory.isChecked()
    tab.inherit.setChecked(True)
    tab.global_memory.setChecked(True)
    tab.save_options()
    tab.refresh()
    assert tab.inherit.isChecked() and tab.global_memory.isChecked()


def choose_pending_action(monkeypatch, text):
    def respond(dialog):
        next(button for button in dialog.buttons() if button.text() == text).click()
        return 0
    monkeypatch.setattr(QMessageBox, "exec", respond)


def test_cancel_session_switch_preserves_editor_and_selected_session(tab, monkeypatch):
    first = tab.session_id()
    second = tab.history.get_session_store().create_session(title="第二个存档", character_name="爱丽丝")
    tab.refresh_sessions()
    tab.content.setPlainText("还没保存的内容")
    choose_pending_action(monkeypatch, "继续编辑")
    tab.sessions.setCurrentIndex(tab.sessions.findData(second.id))
    assert tab.session_id() == first
    assert tab.content.toPlainText() == "还没保存的内容"
    assert tab.dirty
    assert not tab.store.list_memories(first)


def test_save_before_session_switch_writes_to_original_session(tab, monkeypatch):
    first = tab.session_id()
    second = tab.history.get_session_store().create_session(title="第二个存档", character_name="爱丽丝")
    tab.refresh_sessions()
    tab.content.setPlainText("原存档的约定")
    tab.inherit.setChecked(True)
    choose_pending_action(monkeypatch, "保存并继续")
    tab.sessions.setCurrentIndex(tab.sessions.findData(second.id))
    assert tab.session_id() == second.id
    assert [item["content"] for item in tab.store.list_memories(first)] == ["原存档的约定"]
    assert not tab.store.list_memories(second.id)
    assert tab.store.session(first)["mode"] == "character"
    assert tab.store.session(second.id)["mode"] == "fresh"


def test_switch_memory_cancel_and_discard_dont_write_drafts(tab, monkeypatch):
    tab.store.edit(tab.session_id(), {"type":"preference", "content":"第一条"})
    tab.store.edit(tab.session_id(), {"type":"event", "content":"第二条"})
    tab.refresh()
    original_id = tab.current["id"]
    tab.content.setPlainText("草稿内容")
    choose_pending_action(monkeypatch, "继续编辑")
    tab.list.setCurrentRow(1)
    assert tab.current["id"] == original_id
    assert tab.list.currentRow() == 0
    assert tab.content.toPlainText() == "草稿内容"
    choose_pending_action(monkeypatch, "放弃修改")
    tab.list.setCurrentRow(1)
    assert tab.current["id"] != original_id
    assert "草稿内容" not in [m["content"] for m in tab.store.list_memories(tab.session_id())]


def test_record_save_preserves_separate_unsaved_range(tab):
    tab.content.setPlainText("喜欢茶")
    tab.inherit.setChecked(True)
    tab.save_memory()
    assert tab.inherit.isChecked() and tab._options_dirty
    assert "未保存" in tab.save_options_button.text()
    assert tab.store.session(tab.session_id())["mode"] == "fresh"
    tab.save_options()
    assert tab.store.session(tab.session_id())["mode"] == "character"


def test_deleting_record_preserves_unsaved_range_without_extra_prompt(tab, monkeypatch):
    tab.content.setPlainText("要删除的记忆")
    tab.save_memory()
    tab.inherit.setChecked(True)
    monkeypatch.setattr("ui.settings_ui.memory_tab.confirm", lambda *args, **kwargs: True)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: pytest.fail("record deletion must preserve the range draft"))
    tab.delete_memory()
    assert not tab.store.list_memories(tab.session_id())
    assert tab.current is None
    assert tab.inherit.isChecked() and tab._options_dirty
    assert tab.store.session(tab.session_id())["mode"] == "fresh"


def test_recall_dialog_does_not_replace_original_sources_or_draft(tab, monkeypatch):
    tab.source_text.setPlainText("原始聊天出处")
    tab.content.setPlainText("正在编辑的内容")
    seen = []
    def inspect(dialog):
        seen.append(next(label.text() for label in dialog.findChildren(QLabel) if "本轮没有" in label.text()))
        return 0
    monkeypatch.setattr(QDialog, "exec", inspect)
    tab.show_recall()
    assert seen == ["本轮没有使用长期记忆。"]
    assert tab.source_text.toPlainText() == "原始聊天出处"
    assert tab.content.toPlainText() == "正在编辑的内容" and tab.dirty


def test_cancel_close_keeps_memory_editor_open(tab, monkeypatch):
    tab.show()
    tab.content.setPlainText("尚未保存")
    choose_pending_action(monkeypatch, "继续编辑")
    assert tab.close() is False
    assert tab.isVisible() and tab.dirty


def test_compact_memory_editor_keeps_actions_and_scrollable_fields(tab):
    app = QApplication.instance()
    tab.resize(630, 480)
    tab.show()
    app.processEvents()
    tab.new_memory()
    app.processEvents()
    assert tab.editor_panel.isVisible() and not tab.list_panel.isVisible()
    assert not tab.sessions.isVisible()
    assert tab.save_button.isVisible() and tab.back_button.isVisible()
    tab.editor_scroll.verticalScrollBar().setValue(tab.editor_scroll.verticalScrollBar().maximum())
    app.processEvents()
    assert tab.editor_scroll.viewport().rect().contains(tab.source_text.mapTo(tab.editor_scroll.viewport(), tab.source_text.rect().bottomLeft()))
    tab.show_list()
    app.processEvents()
    assert tab.empty_panel.isVisible() and not tab.editor_panel.isVisible()
    assert tab.filter_toggle.isVisible()
