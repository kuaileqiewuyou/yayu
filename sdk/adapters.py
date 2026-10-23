"""SDK 基类：所有适配器的抽象接口。"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class LLMAdapter(ABC):
    """LLM 适配器基类"""

    def __init__(self, **kwargs):
        pass

    @abstractmethod
    def chat(self, messages: list, stream: bool = False, **kwargs):
        """发送消息到 LLM 并获取回复"""
        ...

    def generate(self, messages: list, *, tools=None, generation_config=None):
        """兼容 tool loop 的统一入口；默认桥接到 chat()。"""
        kwargs = {}
        if tools is not None:
            kwargs["tools"] = tools
        if generation_config is not None:
            kwargs["generation_config"] = generation_config
        return self.chat(messages=messages, stream=False, **kwargs)

    @classmethod
    def get_config_schema(cls) -> dict[str, dict]:
        """返回适配器的额外配置字段 schema"""
        return {}


class TTSAdapter(ABC):
    """TTS 适配器基类"""

    def __init__(self, **kwargs):
        pass

    @abstractmethod
    def synthesize(self, text: str, **kwargs) -> Optional[str]:
        """合成语音，返回音频文件路径"""
        ...


class ASRAdapter(ABC):
    """ASR 适配器基类"""

    def __init__(self, **kwargs):
        pass

    @abstractmethod
    def recognize(self, audio_data: bytes, **kwargs) -> str:
        """识别语音，返回文本"""
        ...


class T2IAdapter(ABC):
    """文生图适配器基类"""

    def __init__(self, **kwargs):
        pass

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> Optional[str]:
        """生成图片，返回图片路径"""
        ...
