"""TTS 适配器基类与工厂"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from config.schema import DEFAULT_TTS_VOICE
from core.runtime.cancellation import current_token, check_cancelled, run_async, TurnCancelled


class TTSAdapter(ABC):
    """TTS 适配器抽象基类"""

    @abstractmethod
    def synthesize(
        self,
        text: str,
        speaker: str = "",
        language: str = "ja",
        speed: float = 1.0,
        *,
        ref_audio_path: str = "",
        prompt_text: str = "",
        prompt_lang: str = "",
    ) -> Optional[str]:
        """合成语音，返回音频文件路径"""
        ...

    def shutdown(self):
        """关闭适配器资源"""
        pass


class GPTSoVITSAdapter(TTSAdapter):
    """GPT-SoVITS TTS 适配器"""

    def __init__(self, server_url: str = "http://127.0.0.1:9880",
                 work_path: str = "", **kwargs):
        self.server_url = server_url.rstrip("/")
        self.work_path = work_path

    def synthesize(
        self,
        text: str,
        speaker: str = "",
        language: str = "ja",
        speed: float = 1.0,
        *,
        ref_audio_path: str = "",
        prompt_text: str = "",
        prompt_lang: str = "",
    ) -> Optional[str]:
        import httpx
        import tempfile

        reference_audio = ref_audio_path or speaker
        if not reference_audio:
            print("[TTS] GPT-SoVITS synthesis failed: reference audio is not configured")
            return None
        if not Path(reference_audio).is_file():
            print(f"[TTS] GPT-SoVITS synthesis failed: reference audio does not exist: {reference_audio}")
            return None

        payload = {
            "text": text,
            "text_lang": language,
            "ref_audio_path": reference_audio,
            "prompt_text": prompt_text,
            "prompt_lang": prompt_lang or language,
            "speed_factor": speed,
            "media_type": "wav",
            "streaming_mode": False,
        }

        try:
            endpoint = self.server_url if self.server_url.endswith("/tts") else f"{self.server_url}/tts"
            if current_token() is not None:
                async def request_audio():
                    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                        return await client.post(endpoint, json=payload)
                resp = run_async(request_audio)
            else:
                resp = httpx.post(endpoint, json=payload, timeout=120.0)
            check_cancelled()
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "").lower()
            if "json" in content_type:
                print(f"[TTS] GPT-SoVITS synthesis failed: server returned an error: {resp.text}")
                return None
            tmp = tempfile.NamedTemporaryFile(
                suffix=".wav",
                delete=False,
                dir=self.work_path or None,
            )
            tmp.write(resp.content)
            tmp.close()
            return tmp.name
        except TurnCancelled:
            raise
        except Exception as e:
            print(f"[TTS] GPT-SoVITS 合成失败: {e}")
        return None

class EdgeTTSAdapter(TTSAdapter):
    """Edge TTS 适配器（免费、无需GPU）"""

    def __init__(self, voice: str = DEFAULT_TTS_VOICE, **kwargs):
        self.voice = voice

    def synthesize(
        self,
        text: str,
        speaker: str = "",
        language: str = "ja",
        speed: float = 1.0,
        **kwargs,
    ) -> Optional[str]:
        import asyncio
        import tempfile
        try:
            import edge_tts
        except ImportError:
            print("[TTS] 请安装 edge-tts: pip install edge-tts")
            return None

        voice = speaker or self.voice
        rate = f"+{int((speed - 1) * 100)}%" if speed >= 1 else f"{int((speed - 1) * 100)}%"

        async def _synth():
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.close()  # Windows must release the file before Edge opens it.
            try:
                communicate = edge_tts.Communicate(text, voice, rate=rate)
                await communicate.save(tmp.name)
                check_cancelled()
                return tmp.name
            except BaseException:
                Path(tmp.name).unlink(missing_ok=True)
                raise

        try:
            return run_async(_synth)
        except TurnCancelled:
            raise
        except Exception as e:
            print(f"[TTS] Edge TTS 合成失败: {e}")
            return None


class TTSAdapterFactory:
    """TTS 适配器工厂"""
    _registry = {
        "gpt-sovits": GPTSoVITSAdapter,
        "edge-tts": EdgeTTSAdapter,
    }

    @classmethod
    def register(cls, name: str, adapter_cls):
        cls._registry[name] = adapter_cls

    @classmethod
    def create_adapter(cls, adapter_name: str, **kwargs) -> TTSAdapter:
        adapter_cls = cls._registry.get(adapter_name)
        if adapter_cls is None:
            raise ValueError(f"未知的 TTS 适配器: {adapter_name}，可用: {list(cls._registry.keys())}")
        return adapter_cls(**kwargs)
