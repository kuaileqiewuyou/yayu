"""TTS 管理器"""
from typing import Optional
from tts.tts_adapter import TTSAdapter


class TTSManager:
    """管理 TTS 适配器和语音合成流程"""

    def __init__(self, tts_server_url: str = ""):
        self.tts_server_url = tts_server_url
        self.adapter: Optional[TTSAdapter] = None
        self.language = "ja"
        self.speed = 1.0

    def set_tts_adapter(self, adapter: TTSAdapter):
        self.adapter = adapter

    def set_language(self, lang: str):
        self.language = lang

    def set_speed(self, speed: float):
        self.speed = speed

    def synthesize(
        self,
        text: str,
        speaker: str = "",
        *,
        ref_audio_path: str = "",
        prompt_text: str = "",
        prompt_lang: str = "",
        speed: Optional[float] = None,
    ) -> Optional[str]:
        """合成语音，返回音频文件路径"""
        if not self.adapter:
            return None
        return self.adapter.synthesize(
            text=text,
            speaker=speaker,
            language=self.language,
            speed=self.speed if speed is None else speed,
            ref_audio_path=ref_audio_path,
            prompt_text=prompt_text,
            prompt_lang=prompt_lang,
        )

    def shutdown(self):
        if self.adapter:
            self.adapter.shutdown()
