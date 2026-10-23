"""Window action signal wiring helpers."""
from __future__ import annotations

from typing import Any
from core.runtime.character_selection import get_active_character

from core.runtime.chat_actions import (
    handle_archive_session_requested,
    handle_clear_requested,
    handle_delete_session_requested,
    handle_new_session_requested,
    handle_rename_session_requested,
    handle_reroll_requested,
    handle_switch_session_requested,
    handle_user_send,
    handle_session_skills_requested,
)


def open_settings_window(settings_window: Any) -> None:
    """Show and focus the settings window."""
    settings_window.show()
    settings_window.raise_()
    settings_window.activateWindow()


def wire_window_actions(
    *,
    window: Any,
    chat_history: Any,
    user_input_queue: Any,
    default_char_color: str,
    active_character_name: str = "角色",
    config: Any | None = None,
    settings_window: Any | None = None,
) -> None:
    """Wire top-level chat window action signals to runtime handlers."""
    def _current_color():
        return getattr(get_active_character(config), "color", default_char_color) if config is not None else default_char_color

    def _current_name():
        return getattr(get_active_character(config), "name", active_character_name) if config is not None else active_character_name

    window.user_message_sent.connect(
        lambda text: handle_user_send(window, chat_history, user_input_queue, text)
    )
    window.clear_requested.connect(
        lambda: handle_clear_requested(window, chat_history)
    )
    window.reroll_requested.connect(
        lambda: handle_reroll_requested(
            window,
            chat_history,
            user_input_queue,
            _current_color(),
        )
    )
    if hasattr(window, "new_session_requested"):
        def _on_new_session_requested(preset_name: str) -> None:
            handle_new_session_requested(
                window,
                chat_history,
                _current_color(),
                character_name=_current_name(),
                config=config,
                preset_name=preset_name,
            )

        window.new_session_requested.connect(_on_new_session_requested)
    if hasattr(window, "session_switch_requested"):
        window.session_switch_requested.connect(
            lambda session_id: handle_switch_session_requested(
                window,
                chat_history,
                _current_color(),
                session_id,
            )
        )
    if hasattr(window, "session_rename_requested"):
        window.session_rename_requested.connect(
            lambda session_id, title: handle_rename_session_requested(
                window,
                chat_history,
                session_id,
                title,
            )
        )
    if hasattr(window, "session_delete_requested"):
        window.session_delete_requested.connect(
            lambda session_id: handle_delete_session_requested(
                window,
                chat_history,
                _current_color(),
                session_id,
            )
        )
    if hasattr(window, "session_archive_requested"):
        window.session_archive_requested.connect(
            lambda session_id, archived: handle_archive_session_requested(
                window,
                chat_history,
                _current_color(),
                session_id,
                archived,
            )
        )
    if hasattr(window, "session_skills_requested"):
        window.session_skills_requested.connect(
            lambda session_id: handle_session_skills_requested(
                window,
                chat_history,
                config,
                session_id,
            )
        )
    if settings_window is not None:
        window.settings_requested.connect(lambda: open_settings_window(settings_window))

    sessions = [
        {
            "id": session.id,
            "title": session.title,
            "updated_at": session.updated_at,
            "archived": session.archived,
            "enabled_skills": list(getattr(session, "enabled_skills", [])),
        }
        for session in chat_history.list_sessions(include_archived=True)
    ] if hasattr(chat_history, "list_sessions") else []
    if hasattr(window, "set_session_list"):
        active_session_id = chat_history.get_active_session_id() if hasattr(chat_history, "get_active_session_id") else ""
        window.set_session_list(sessions, active_session_id or "")
