"""聊天窗口动作处理辅助函数。

这些函数把主入口里的用户动作处理逻辑拆出来，保持 main.py 更接近
Qt 对象组装和信号连接层；函数本身只依赖传入的窗口、历史模块和队列，
便于单元测试。
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QDialog, QListWidget, QListWidgetItem, QPushButton, QMessageBox
from PySide6.QtCore import Qt

from core.runtime.chat_display import restore_chat_history_to_window
from core.skills.repository import SkillRepository
from ui.frameless_dialog import build_frameless_dialog_shell


NO_RETRY_MESSAGE = "没有可重试的上一轮对话"


def _cancel_turn(window):
    cancel = getattr(window, "cancel_current_turn", None)
    if callable(cancel):
        cancel(notify=False)


def _enqueue_turn(window, queue, text):
    enqueue = getattr(window, "enqueue_turn", None)
    if callable(enqueue):
        enqueue(text)
    else:
        queue.put(text)


def _refresh_window_from_current_session(window: Any, history: Any, default_char_color: str) -> None:
    window.clear_messages()
    restore_chat_history_to_window(
        window,
        history.get_history(),
        default_char_color=default_char_color,
    )


def handle_user_send(window: Any, history: Any, user_input_queue: Any, text: str) -> None:
    """处理用户发送文本。"""
    window.set_waiting_for_reply(True)
    window.set_reply_status("已发送，等待模型回复...")
    history.add_to_history("user", text)
    _enqueue_turn(window, user_input_queue, text)


def handle_clear_requested(window: Any, history: Any) -> None:
    """处理清空对话历史请求。弹出二次确认弹窗，防止误操作。"""
    if not _confirm_clear(window):
        return
    _cancel_turn(window)
    history.clear_history()
    window.clear_messages()
    window.clear_reply_status()
    window.set_reply_status("对话历史已清空")


def _confirm_clear(window: Any) -> bool:
    """弹出二次确认弹窗，返回用户是否确认清空。

    测试可通过 monkeypatch 此函数来跳过 GUI 交互。
    """
    reply = QMessageBox.question(
        window,
        "确认清空",
        "确定要清空当前对话历史吗？\n此操作不可撤销。",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return reply == QMessageBox.StandardButton.Yes


def handle_reroll_requested(
    window: Any,
    history: Any,
    user_input_queue: Any,
    default_char_color: str,
) -> None:
    """处理重试上一轮对话请求。"""
    retry_text = history.get_last_user_content()
    if not retry_text:
        window.set_reply_status(NO_RETRY_MESSAGE, error=True)
        return
    _cancel_turn(window)
    if not history.pop_last_turn():
        window.set_reply_status(NO_RETRY_MESSAGE, error=True)
        return

    _refresh_window_from_current_session(window, history, default_char_color)
    window.set_waiting_for_reply(True)
    window.set_reply_status("正在重新生成上一轮回复...")
    history.add_to_history("user", retry_text)
    window.add_message(retry_text, is_user=True)
    _enqueue_turn(window, user_input_queue, retry_text)


def resolve_new_session_skill_selection(config: Any | None, preset_name: str | None) -> list[str]:
    if config is None:
        return []

    default_skills = list(getattr(config, "default_skills", []) or [])
    if not preset_name or preset_name == "全局默认":
        return default_skills

    for preset in getattr(config, "skill_presets", []) or []:
        if getattr(preset, "name", None) == preset_name:
            return list(getattr(preset, "skills", []) or [])

    return default_skills


def handle_new_session_requested(
    window: Any,
    history: Any,
    default_char_color: str,
    *,
    character_name: str,
    config: Any | None = None,
    preset_name: str | None = None,
) -> None:
    _cancel_turn(window)
    existing = history.list_sessions()
    title = f"新会话 {len(existing) + 1}"
    enabled_skills = resolve_new_session_skill_selection(config, preset_name)
    memory_mode = getattr(window, "_new_session_memory_mode", "fresh")
    if memory_mode == "checkpoint" and callable(getattr(history, "continue_session", None)):
        session = history.continue_session(getattr(window, "_new_session_source_id", ""))
        if session is None:
            window.set_reply_status("接续失败：未找到存档", error=True)
            return
    else:
        session = history.create_session(
            title=title, character_name=character_name, make_active=True, enabled_skills=enabled_skills)
        if callable(getattr(history, "configure_memory", None)):
            history.configure_memory(session.id, mode="character" if memory_mode == "character" else "fresh")
    window._new_session_memory_mode = "fresh"
    _refresh_window_from_current_session(window, history, default_char_color)
    window.set_reply_status(f"已创建并切换到会话：{session.title}")
    _sync_session_list_to_window(window, history)


def handle_switch_session_requested(window: Any, history: Any, default_char_color: str, session_id: str) -> None:
    _cancel_turn(window)
    if not history.switch_session(session_id):
        window.set_reply_status("切换会话失败：未找到目标会话", error=True)
        return
    _refresh_window_from_current_session(window, history, default_char_color)
    _sync_session_list_to_window(window, history)
    active_id = history.get_active_session_id()
    title = next((session.title for session in history.list_sessions(include_archived=True) if session.id == active_id), "")
    window.set_reply_status(f"已切换到会话：{title}")


def handle_rename_session_requested(window: Any, history: Any, session_id: str, title: str) -> None:
    session = history.rename_session(session_id, title)
    if session is None:
        window.set_reply_status("重命名会话失败：未找到目标会话", error=True)
        return
    _sync_session_list_to_window(window, history)
    window.set_reply_status(f"已重命名会话：{session.title}")


def handle_archive_session_requested(window: Any, history: Any, default_char_color: str, session_id: str, archived: bool) -> None:
    _cancel_turn(window)
    session = history.archive_session(session_id, archived=archived)
    if session is None:
        window.set_reply_status("归档会话失败：未找到目标会话", error=True)
        return
    active_id = history.get_active_session_id()
    if archived and active_id == session_id:
        remaining_sessions = history.list_sessions(include_archived=False)
        next_session = next((item for item in remaining_sessions if item.id != session_id), None)
        if next_session is None:
            next_session = history.create_session(title="新会话 1", character_name=session.character_name, make_active=True)
        else:
            history.switch_session(next_session.id)
        _refresh_window_from_current_session(window, history, default_char_color)
    _sync_session_list_to_window(window, history)
    action = "已归档" if archived else "已恢复"
    window.set_reply_status(f"{action}会话：{session.title}")


def build_session_skills_dialog(window: Any, history: Any, config: Any, session_id: str) -> QDialog | None:
    repository = SkillRepository([config.skills_root])
    available_skills = repository.list_skills()
    session = history.get_session_store().get_session(session_id)
    if session is None:
        window.set_reply_status("编辑会话技能失败：未找到目标会话", error=True)
        return None

    dialog = QDialog(window)
    dialog.resize(460, 390)
    layout = build_frameless_dialog_shell(
        dialog,
        f"会话技能：{session.title}",
        close_object_name="session_skills_close_button",
        close_accessible_name="Close session skills",
        close_tool_tip="关闭会话技能",
    )

    list_widget = QListWidget(dialog)
    enabled = set(session.enabled_skills)
    for skill in available_skills:
        item = QListWidgetItem(f"{skill.name} — {skill.description}")
        item.setData(Qt.ItemDataRole.UserRole, skill.name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if skill.name in enabled else Qt.CheckState.Unchecked)
        list_widget.addItem(item)
    layout.addWidget(list_widget)

    save_btn = QPushButton("保存")
    cancel_btn = QPushButton("取消")
    save_btn.setObjectName("session_skills_save_button")
    cancel_btn.setObjectName("session_skills_cancel_button")
    layout.addWidget(save_btn)
    layout.addWidget(cancel_btn)

    def _save() -> None:
        selected = []
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.data(Qt.ItemDataRole.UserRole))
        history.update_session_enabled_skills(session_id, selected)
        _sync_session_list_to_window(window, history)
        window.set_reply_status(f"已更新会话技能：{session.title}")
        dialog.accept()

    save_btn.clicked.connect(_save)
    cancel_btn.clicked.connect(dialog.reject)
    return dialog


def handle_session_skills_requested(window: Any, history: Any, config: Any, session_id: str) -> None:
    dialog = build_session_skills_dialog(window, history, config, session_id)
    if dialog is None:
        return
    dialog.exec()


def handle_delete_session_requested(window: Any, history: Any, default_char_color: str, session_id: str) -> None:
    _cancel_turn(window)
    removed = history.delete_session(session_id)
    if not removed:
        window.set_reply_status("删除会话失败：未找到目标会话", error=True)
        return
    _refresh_window_from_current_session(window, history, default_char_color)
    _sync_session_list_to_window(window, history)
    window.set_reply_status("已删除会话")


def _sync_session_list_to_window(window: Any, history: Any) -> None:
    sessions = [
        {
            "id": session.id,
            "title": session.title,
            "updated_at": session.updated_at,
            "archived": session.archived,
            "enabled_skills": list(getattr(session, "enabled_skills", [])),
        }
        for session in history.list_sessions(include_archived=True)
    ]
    window.set_session_list(sessions, history.get_active_session_id() or "")
