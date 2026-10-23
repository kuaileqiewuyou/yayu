"""TTS 管理器初始化辅助。"""

from __future__ import annotations

from typing import Any

from config.schema import DEFAULT_TTS_VOICE
from tts.tts_manager import TTSManager


def create_tts_manager(config: Any) -> TTSManager:
    """根据配置创建并初始化 TTSManager。

    保持主入口原有行为：provider 为空或 none 时只创建基础 manager；
    provider 初始化失败时打印错误并返回禁用 adapter 的 manager。
    """
    tts_manager = TTSManager(tts_server_url=config.api_config.gpt_sovits_url)
    tts_provider = config.api_config.tts_provider
    if tts_provider and tts_provider != "none":
        from tts.tts_adapter import TTSAdapterFactory
        try:
            tts_kwargs = {}
            if tts_provider == "gpt-sovits":
                tts_kwargs["server_url"] = config.api_config.gpt_sovits_url
            elif tts_provider == "edge-tts":
                tts_voice = config.api_config.tts_voice
                tts_kwargs["voice"] = tts_voice if tts_voice.strip() else DEFAULT_TTS_VOICE
            tts_adapter = TTSAdapterFactory.create_adapter(tts_provider, **tts_kwargs)
            tts_manager.set_tts_adapter(tts_adapter)
            tts_manager.set_language(config.system_config.voice_language)
            tts_manager.set_speed(config.api_config.tts_speed)
            print(f"[TTS] 已启用: {tts_provider}")
        except Exception as e:
            print(f"[TTS] 初始化失败: {e}，语音功能已禁用")
    return tts_manager
