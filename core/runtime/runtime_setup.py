"""Runtime and queue assembly helpers."""
from __future__ import annotations

from dataclasses import dataclass
from queue import Queue
from typing import TYPE_CHECKING

from core.runtime.app_runtime import AppRuntime, set_app_runtime

if TYPE_CHECKING:
    from config.config_manager import ConfigManager
    from llm.llm_manager import LLMManager
    from tts.tts_manager import TTSManager


@dataclass
class RuntimeSetup:
    """Application runtime plus queues shared by workers and UI actions."""

    runtime: AppRuntime
    user_input_queue: Queue
    tts_queue: Queue
    audio_path_queue: Queue
    t2i_prompt_queue: Queue


def create_runtime_setup(
    config: "ConfigManager",
    llm_manager: "LLMManager",
    tts_manager: "TTSManager",
) -> RuntimeSetup:
    """Create queues, build AppRuntime, and register it globally."""
    user_input_queue = Queue()
    tts_queue = Queue()
    audio_path_queue = Queue()
    t2i_prompt_queue = Queue()

    runtime = AppRuntime(
        config=config,
        llm_manager=llm_manager,
        tts_manager=tts_manager,
        user_input_queue=user_input_queue,
        tts_queue=tts_queue,
        audio_path_queue=audio_path_queue,
    )
    set_app_runtime(runtime)

    return RuntimeSetup(
        runtime=runtime,
        user_input_queue=user_input_queue,
        tts_queue=tts_queue,
        audio_path_queue=audio_path_queue,
        t2i_prompt_queue=t2i_prompt_queue,
    )
