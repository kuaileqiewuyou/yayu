"""Chat application bootstrap and lifecycle coordinator."""
from __future__ import annotations

import sys

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from PySide6.QtWidgets import QApplication

from config.config_manager import ConfigManager
from core.mcp.runtime_controller import MCPRuntimeController
from core.mcp.status import MCPStatusSnapshot
from core.security.bootstrap import PROJECT_ROOT, load_allowed_roots
from core.runtime.app_runtime import clear_app_runtime
from core.runtime.application_identity import CHAT_APP_ID, apply_application_icon, prepare_application_identity
from core.runtime.audio_player import AudioPlayer
from core.runtime.lazy_settings import LazySettingsWindow
from core.runtime.chat_display import restore_chat_history_to_window
from core.runtime.llm_setup import create_llm_runtime_context, build_active_character_template
from core.runtime.character_selection import get_active_character, get_active_character_index
from llm.tools.builtin_tools import register_builtin_tools, register_configured_web_tools
from core.runtime.runtime_setup import create_runtime_setup
from core.runtime.signal_wiring import wire_runtime_signals
from core.runtime.sprite_controller import SpriteController, build_sprite_map
from core.runtime.startup_notices import apply_llm_config_startup_notice, apply_mcp_status_startup_notice
from core.runtime.t2i_setup import create_t2i_manager
from core.runtime.tts_setup import create_tts_manager
from core.runtime.runtime_lifecycle import run_runtime_event_loop
from core.runtime.worker_lifecycle import create_runtime_workers
from core.sprite import chat_history
from i18n import init_i18n
from llm.tools.tool_manager import ToolManager
from ui.chat_ui.chat_ui import ChatUIWindow
from ui.motion import apply_system_config as apply_motion_preferences
from ui.theme import dialogs_qss


@dataclass
class ChatAppHandles:
    """Objects that must stay alive for the chat app runtime lifecycle."""

    app: QApplication
    config: ConfigManager
    llm_context: Any
    tts_manager: Any
    t2i_manager: Any
    runtime_setup: Any
    workers: Any
    window: ChatUIWindow
    settings_window: LazySettingsWindow
    sprite_controller: SpriteController
    audio_player: AudioPlayer
    signal_wiring_handles: Any
    chat_history: Any
    mcp_controller: MCPRuntimeController


@dataclass
class CoreRuntimeComponents:
    """Core runtime components created before history, workers, and UI."""

    llm_context: Any
    tts_manager: Any
    t2i_manager: Any
    runtime_setup: Any
    mcp_controller: MCPRuntimeController
    mcp_status: MCPStatusSnapshot


def load_mcp_tools_into_tool_manager(config: ConfigManager, manager: Any) -> tuple[MCPRuntimeController, MCPStatusSnapshot]:
    controller = MCPRuntimeController(config_path=config._MCP_CONFIG_PATH)
    snapshot = controller.register_into_tool_manager(manager)
    return controller, snapshot


def create_core_runtime_components(config: ConfigManager) -> CoreRuntimeComponents:
    """Create the core runtime components in bootstrap order."""
    llm_context = create_llm_runtime_context(config)
    tool_manager = ToolManager()
    register_builtin_tools(tool_manager, allowed_roots=load_allowed_roots())
    register_configured_web_tools(tool_manager, config.api_config)
    tts_manager = create_tts_manager(config)
    t2i_manager = create_t2i_manager(config)
    runtime_setup = create_runtime_setup(config, llm_context.manager, tts_manager)
    runtime_setup.runtime.tool_manager = tool_manager
    mcp_controller, mcp_status = load_mcp_tools_into_tool_manager(config, tool_manager)
    return CoreRuntimeComponents(
        llm_context=llm_context,
        tts_manager=tts_manager,
        t2i_manager=t2i_manager,
        runtime_setup=runtime_setup,
        mcp_controller=mcp_controller,
        mcp_status=mcp_status,
    )


def create_runtime_workers_after_history_load(
    runtime_setup: Any,
    t2i_manager: Any,
    history_store: Any,
    *,
    default_session_title: str = "默认会话",
    character_name: str = "",
) -> Any:
    """Load active session history before creating runtime workers."""
    runtime_setup.history_recovery_notice = ""
    runtime = getattr(runtime_setup, "runtime", None)
    config = getattr(runtime, "config", None)
    manager = getattr(runtime, "llm_manager", None)

    def rebuild_template():
        # Session skills belong to the selected session. Building before its
        # pointer is chosen could reuse the previous character's skill set.
        if config is not None and callable(getattr(manager, "set_messages", None)):
            template = build_active_character_template(config)
            manager.user_template = template
            manager.set_messages([{"role": "system", "content": template}] if template else [])

    if hasattr(history_store, "ensure_default_session") and hasattr(history_store, "get_active_session_id"):
        history_store.ensure_default_session(title=default_session_title, character_name=character_name)
        active_session_id = history_store.get_active_session_id()
        rebuild_template()
        if active_session_id and hasattr(history_store, "load_session"):
            loaded = history_store.load_session(active_session_id)
        else:
            loaded = history_store.load()
    else:
        rebuild_template()
        loaded = history_store.load()
    if loaded is False:
        creator = getattr(history_store, "create_session", None)
        if not callable(creator):
            raise RuntimeError("聊天记录无法读取，已停止启动以保留原文件")
        character = get_active_character(config) if config is not None else None
        system = getattr(config, "system_config", None)
        defaults = [*(getattr(system, "default_skills", []) or []),
                    *(getattr(character, "default_skills", []) or [])]
        enabled = list(dict.fromkeys(str(skill).strip() for skill in defaults if str(skill).strip()))
        # The new empty session establishes its own pointer; no damaged payload
        # is loaded or saved. Rebuild again for this session before continuing.
        session = creator(title=default_session_title, character_name=getattr(character, "name", character_name),
                          make_active=True, enabled_skills=enabled)
        rebuild_template()
        if history_store.load_session(session.id) is not True:
            raise RuntimeError("无法打开安全的新会话，已停止启动以保留原聊天记录")
        runtime_setup.history_recovery_notice = "该角色的旧聊天记录暂时无法读取，原文件已保留，已打开独立的新会话。"
    return create_runtime_workers(runtime_setup, t2i_manager=t2i_manager)


def create_initial_chat_display(window: ChatUIWindow, config: ConfigManager, llm_context: Any, history_store: Any) -> SpriteController:
    """Restore initial chat messages and create the sprite controller."""
    set_active_name = getattr(window, "set_active_character_name", None)
    if callable(set_active_name):
        set_active_name(getattr(llm_context, "active_character_name", ""))
    restore_chat_history_to_window(
        window,
        history_store.get_history(),
        default_char_color=llm_context.active_character_color,
    )
    character_index = get_active_character_index(config)
    sprite_map = build_sprite_map(config.characters, character_index=character_index)
    controller = SpriteController(window, config.characters, sprite_map)
    controller.character_index = character_index
    controller.show_default_sprite()
    return controller


def create_settings_window():
    from ui.settings_ui.window import SettingsWindow
    return SettingsWindow()


def create_chat_windows(config: ConfigManager) -> tuple[ChatUIWindow, LazySettingsWindow]:
    """Create chat UI windows and apply startup notices in bootstrap order."""
    window = ChatUIWindow()
    apply_llm_config_startup_notice(window, config)
    window.configure_tts_connection_status(
        config.api_config.tts_provider,
        config.api_config.gpt_sovits_url,
    )
    settings_window = LazySettingsWindow(create_settings_window)
    if hasattr(window, "set_always_on_top"):
        window.set_always_on_top(getattr(config.system_config, "always_on_top", False))
        settings_window.always_on_top_changed.connect(window.set_always_on_top)
        settings_window.set_owner_window(window)
    if hasattr(window, "background_requested"):
        from core.runtime.manual_background import ManualBackgroundController
        window._background_controller = ManualBackgroundController(window, config, settings_window)
        window._background_controller.restore()
    return window, settings_window


def build_chat_app(argv: Sequence[str] | None = None) -> ChatAppHandles:
    """Build the chat application graph without entering the Qt event loop."""
    prepare_application_identity(CHAT_APP_ID)
    app = QApplication(list(sys.argv if argv is None else argv))
    apply_application_icon(app)
    app.setStyleSheet(dialogs_qss())

    config = ConfigManager()
    init_i18n(config.system_config.ui_language)
    apply_motion_preferences(config.system_config)

    components = create_core_runtime_components(config)
    llm_context = components.llm_context
    tts_manager = components.tts_manager
    t2i_manager = components.t2i_manager
    runtime_setup = components.runtime_setup

    workers = create_runtime_workers_after_history_load(
        runtime_setup,
        t2i_manager,
        chat_history,
        default_session_title="默认会话",
        character_name=llm_context.active_character_name,
    )

    window, settings_window = create_chat_windows(config)
    apply_mcp_status_startup_notice(window, components.mcp_status)
    settings_window.set_mcp_runtime_controller(components.mcp_controller)
    settings_window.refresh_mcp_status(components.mcp_status)
    sprite_controller = create_initial_chat_display(window, config, llm_context, chat_history)

    audio_player = AudioPlayer()
    signal_wiring_handles = wire_runtime_signals(
        window=window,
        workers=workers,
        runtime_setup=runtime_setup,
        llm_context=llm_context,
        chat_history=chat_history,
        config=config,
        sprite_controller=sprite_controller,
        audio_player=audio_player,
        settings_window=settings_window,
    )

    recovery_notice = getattr(runtime_setup, "history_recovery_notice", "")
    if recovery_notice:
        window.set_reply_status(recovery_notice, error=True)

    return ChatAppHandles(
        app=app,
        config=config,
        llm_context=llm_context,
        tts_manager=tts_manager,
        t2i_manager=t2i_manager,
        runtime_setup=runtime_setup,
        workers=workers,
        window=window,
        settings_window=settings_window,
        sprite_controller=sprite_controller,
        audio_player=audio_player,
        signal_wiring_handles=signal_wiring_handles,
        chat_history=chat_history,
        mcp_controller=components.mcp_controller,
    )


def run_chat_app(argv: Sequence[str] | None = None) -> int:
    """Build and run the chat application, cleaning up workers and history."""
    try:
        handles = build_chat_app(argv)
    except Exception:
        clear_app_runtime()
        raise

    return run_runtime_event_loop(handles)
