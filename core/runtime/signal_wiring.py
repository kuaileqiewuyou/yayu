"""Runtime signal wiring helpers.

This module keeps main.py focused on object creation while preserving the
original signal-to-slot wiring and the lifetime of handler objects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.runtime.audio_player import AudioPlayer
from core.runtime.cg_ui_handlers import handle_t2i_image_generated
from core.runtime.llm_ui_handlers import LLMUiHandlers
from core.runtime.ui_worker_handlers import UIWorkerHandlers
from core.runtime.window_action_wiring import wire_window_actions


@dataclass
class SignalWiringHandles:
    """Objects that must stay alive for Qt signal callbacks."""

    llm_ui_handlers: LLMUiHandlers
    ui_worker_handlers: UIWorkerHandlers
    turn_controller: Any = None
    character_controller: Any = None


def wire_t2i_worker_signals(window: Any, t2i_worker: Any) -> None:
    """Wire T2I worker result signals to chat-window UI updates."""
    t2i_worker.image_generated.connect(
        lambda path: handle_t2i_image_generated(window, path)
    )
    t2i_worker.generation_failed.connect(
        lambda message: window.set_reply_status(message, error=True)
    )


def wire_runtime_signals(
    *,
    window: Any,
    workers: Any,
    runtime_setup: Any,
    llm_context: Any,
    chat_history: Any,
    config: Any,
    sprite_controller: Any,
    audio_player: AudioPlayer,
    settings_window: Any | None = None,
) -> SignalWiringHandles:
    """Wire runtime workers and window actions exactly as main.py did.

    ``stream_chunk`` is intentionally not connected: parsed dialog events are
    the UI boundary, and raw stream chunks may contain incomplete JSON.
    """
    llm_worker = workers.llm_worker
    ui_worker = workers.ui_worker

    llm_ui_handlers = LLMUiHandlers(
        window=window,
        history=chat_history,
        active_character_name=llm_context.active_character_name,
        char_color=llm_context.active_character_color,
        set_sprite_by_id=sprite_controller.set_sprite_by_id,
    )

    # LLMWorker signals.
    llm_worker.status_changed.connect(
        lambda text: window.set_reply_status(text, error=text.startswith("回复失败"))
    )
    llm_worker.stream_start.connect(llm_ui_handlers.on_stream_start)
    llm_worker.dialog_parsed.connect(llm_ui_handlers.on_dialog_parsed)
    llm_worker.tool_summary_ready.connect(window.set_tool_summary_result)
    llm_worker.stream_end.connect(llm_ui_handlers.on_stream_end)
    llm_worker.error.connect(llm_ui_handlers.on_llm_error)


    submit_t2i_prompt = None
    t2i_worker = getattr(workers, "t2i_worker", None)
    if t2i_worker is not None:
        submit_t2i_prompt = runtime_setup.t2i_prompt_queue.put

    ui_worker_handlers = UIWorkerHandlers(
        window=window,
        config=config,
        play_audio=audio_player.play,
        submit_t2i_prompt=submit_t2i_prompt,
    )
    ui_worker.update_dialog.connect(ui_worker_handlers.on_update_dialog)
    ui_worker.update_narration.connect(ui_worker_handlers.on_update_narration)
    ui_worker.update_options.connect(ui_worker_handlers.on_update_options)
    ui_worker.update_cg.connect(ui_worker_handlers.on_update_cg)
    ui_worker.update_stat.connect(ui_worker_handlers.on_update_stat)
    ui_worker.update_cot.connect(ui_worker_handlers.on_update_cot)

    if t2i_worker is not None:
        wire_t2i_worker_signals(window, t2i_worker)

    wire_window_actions(
        window=window,
        chat_history=chat_history,
        user_input_queue=runtime_setup.user_input_queue,
        default_char_color=llm_context.active_character_color,
        active_character_name=llm_context.active_character_name,
        config=config,
        settings_window=settings_window,
    )

    turn_controller = None
    if hasattr(llm_worker, "turn_event") and hasattr(window, "stop_requested"):
        from core.runtime.turn_controller import TurnController
        turn_controller = TurnController(
            window, workers, runtime_setup, chat_history, llm_ui_handlers,
            ui_worker_handlers, audio_player, settings_window,
        )

    character_controller = None
    if hasattr(window, "character_requested"):
        from core.runtime.character_switch import CharacterSwitchController
        character_controller = CharacterSwitchController(
            window, config, chat_history, llm_context, sprite_controller,
            llm_ui_handlers, turn_controller, settings_window,
        )
        window._character_controller = character_controller
        if (hasattr(window, "reply_waiting_changed")
                and callable(getattr(settings_window, "set_character_switch_enabled", None))):
            window.reply_waiting_changed.connect(
                lambda waiting: settings_window.set_character_switch_enabled(not waiting)
            )

    return SignalWiringHandles(
        llm_ui_handlers=llm_ui_handlers,
        ui_worker_handlers=ui_worker_handlers,
        turn_controller=turn_controller,
        character_controller=character_controller,
    )
