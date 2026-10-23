"""ASR 语音识别适配器"""
from abc import ABC, abstractmethod
from typing import Optional


class ASRAdapter(ABC):
    """ASR 适配器抽象基类"""

    @abstractmethod
    def recognize(self, audio_path: str) -> Optional[str]:
        """识别音频文件，返回文本"""
        ...


class VoskAdapter(ASRAdapter):
    """Vosk 离线语音识别"""

    def __init__(self, model_path: str = "", language: str = "ja"):
        self.model_path = model_path
        self.language = language
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from vosk import Model
                self._model = Model(self.model_path) if self.model_path else Model(lang=self.language)
            except Exception as e:
                print(f"[ASR] Vosk 模型加载失败: {e}")
        return self._model

    def recognize(self, audio_path: str) -> Optional[str]:
        import json
        import wave
        try:
            from vosk import KaldiRecognizer
        except ImportError:
            print("[ASR] 请安装 vosk: pip install vosk")
            return None

        model = self._get_model()
        if not model:
            return None

        try:
            wf = wave.open(audio_path, "rb")
            rec = KaldiRecognizer(model, wf.getframerate())
            rec.SetWords(True)

            results = []
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                if rec.AcceptWaveform(data):
                    part = json.loads(rec.Result())
                    results.append(part.get("text", ""))

            final = json.loads(rec.FinalResult())
            results.append(final.get("text", ""))
            wf.close()
            return " ".join(results).strip()
        except Exception as e:
            print(f"[ASR] 识别失败: {e}")
            return None


def system_config_to_asr_lang(system_config) -> str:
    """从系统配置推断 ASR 语言"""
    lang = getattr(system_config, "voice_language", "ja")
    if lang in ("zh", "zh_CN", "chinese"):
        return "zh"
    elif lang in ("en", "english"):
        return "en"
    return "ja"
