"""Switch persona, history and artwork as one GUI-thread operation."""
from __future__ import annotations

from contextlib import nullcontext
import copy

from core.runtime.character_selection import (
    character_choices, get_active_character, get_active_character_index,
)
from core.runtime.chat_display import restore_chat_history_to_window
from core.runtime.llm_setup import build_active_character_template
from core.runtime.chat_actions import _sync_session_list_to_window


class CharacterSwitchController:
    def __init__(self, window, config, history, llm_context, sprite_controller,
                 llm_handlers, turn_controller=None, settings_window=None):
        self.window, self.config, self.history = window, config, history
        self.context, self.sprites, self.handlers = llm_context, sprite_controller, llm_handlers
        self.turns, self.settings = turn_controller, settings_window
        self.switching = False
        self.drafts = {}
        character = get_active_character(config)
        self.active_id = getattr(character, "memory_id", "")
        for signal in (getattr(window, "character_requested", None),
                       getattr(settings_window, "character_selected", None)):
            if signal is not None:
                signal.connect(self.select)
        opening = getattr(window, "character_menu_opening", None)
        if opening is not None:
            opening.connect(self._sync_selection)
        self._sync_selection()

    def _sync_selection(self):
        character = get_active_character(self.config)
        self.active_id = getattr(character, "memory_id", "")
        if callable(getattr(self.window, "set_character_list", None)):
            self.window.set_character_list(character_choices(self.config), self.active_id)
        if callable(getattr(self.window, "set_active_character_name", None)):
            self.window.set_active_character_name(getattr(character, "name", ""))
        if callable(getattr(self.settings, "set_active_character_id", None)):
            self.settings.set_active_character_id(self.active_id)

    def _refresh_display(self):
        character = get_active_character(self.config)
        self.context.active_character_name = getattr(character, "name", "角色")
        self.context.active_character_color = getattr(character, "color", "#f2a0bd")
        self.handlers.active_character_name = self.context.active_character_name
        self.handlers.char_color = self.context.active_character_color
        self._sync_selection()
        self.window.clear_messages()
        if callable(getattr(self.window, "set_tool_summary_result", None)):
            self.window.set_tool_summary_result(None)
        input_edit = getattr(self.window, "input_edit", None)
        if input_edit is not None:
            input_edit.setText(self.drafts.get(self.active_id, ""))
        restore_chat_history_to_window(
            self.window, self.history.get_history(), default_char_color=self.context.active_character_color,
        )
        self.sprites.select_character(self.config.characters, get_active_character_index(self.config))
        _sync_session_list_to_window(self.window, self.history)
        service = getattr(self.turns, "memory_service", None)
        if service is not None:
            service.character_names = {character.memory_id: character.name for character in self.config.characters}

    def select(self, character_id: str) -> bool:
        if self.switching or bool(getattr(self.turns, "closing", False)):
            return False
        matches = [character for character in self.config.characters
                   if getattr(character, "memory_id", "") == character_id]
        if not character_id or len(matches) != 1:
            self.window.set_reply_status("无法切换：角色不存在或标识重复，请在设置中检查。", error=True)
            return False
        if character_id == self.active_id:
            self._sync_selection()
            return True

        self.switching = True
        manager = self.context.manager
        old_identity = self.config.system_config.active_character_id
        old_session = self.history.get_active_session_id()
        old_template = manager.user_template
        old_messages = None
        old_history = None
        input_edit = getattr(self.window, "input_edit", None)
        if input_edit is not None:
            self.drafts[self.active_id] = input_edit.text()
        try:
            # Cancellation commits partial output to the OLD session, and marks
            # queued audio, choices, images and model results as stale.
            cancel = getattr(self.window, "cancel_current_turn", None)
            if callable(cancel):
                cancel(notify=False)
            self.history.save()
            old_messages = copy.deepcopy(manager.get_messages())
            old_history = copy.deepcopy(self.history.get_history())
            transaction = getattr(self.config, "character_selection_transaction",
                                  getattr(self.config, "persistence_transaction", nullcontext))
            with transaction():
                self.config.system_config.active_character_id = character_id
                session = self.history.ensure_character_session(
                    character_id=character_id, character_name=matches[0].name,
                )
                template = build_active_character_template(self.config)
                manager.user_template = template
                # set_template alone keeps the outgoing role's conversation.
                manager.set_messages([{"role": "system", "content": template}] if template else [])
                if not self.history.load_session(session.id):
                    raise ValueError("该角色的聊天记录无法读取，原文件已保留")
                self.config.save_characters()
                self.config.save_system_config()
                self._refresh_display()
            self.window.set_reply_status(f"已切换为{matches[0].name}，继续该角色的聊天。")
            return True
        except Exception as exc:
            self.config.system_config.active_character_id = old_identity
            manager.user_template = old_template
            restored = True
            if old_messages is not None:
                try:
                    if old_session:
                        restored = bool(self.history.load_session(old_session))
                except Exception:
                    restored = False
                manager.set_messages(old_messages)
                self.history.get_history()[:] = old_history
            if old_messages is not None and restored:
                self._refresh_display()
            else:
                self._sync_selection()
            if not restored:
                # A failed disk rollback must not let a subsequent send use a
                # different session pointer with the old persona/history.
                for name in ("input_edit", "send_btn"):
                    control = getattr(self.window, name, None)
                    if control is not None:
                        control.setEnabled(False)
            self.window.set_reply_status(f"角色切换失败：{exc}。当前聊天已保留。", error=True)
            return False
        finally:
            self.switching = False
