"""全局运行时上下文，持有各 Manager 实例引用。"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
from queue import Queue

if TYPE_CHECKING:
    from config.config_manager import ConfigManager
    from llm.llm_manager import LLMManager
    from tts.tts_manager import TTSManager

_app_runtime: Optional["AppRuntime"] = None


@dataclass
class AppRuntime:
    """应用运行时上下文，各模块通过 get_app_runtime() 获取。"""
    config: "ConfigManager"
    llm_manager: "LLMManager"
    tts_manager: Optional["TTSManager"] = None
    user_input_queue: Queue = field(default_factory=Queue)
    tts_queue: Queue = field(default_factory=Queue)
    audio_path_queue: Queue = field(default_factory=Queue)


def set_app_runtime(rt: AppRuntime) -> None:
    global _app_runtime
    _app_runtime = rt


def clear_app_runtime() -> None:
    """Clear the globally registered application runtime."""
    global _app_runtime
    _app_runtime = None


def get_app_runtime() -> AppRuntime:
    if _app_runtime is None:
        raise RuntimeError("AppRuntime 尚未初始化")
    return _app_runtime


def try_get_app_runtime() -> Optional[AppRuntime]:
    return _app_runtime
