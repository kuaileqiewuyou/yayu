"""LLM 适配器实现：支持 OpenAI 兼容接口、DeepSeek、Claude 等。"""
import json
import time
from typing import Any, Dict, List, Optional
from threading import Lock

from sdk.adapters import LLMAdapter


# 各适配器支持的参数白名单
SUPPORTED_CHAT_PARAMS = {
    "DeepSeekAdapter": {
        "temperature", "presence_penalty", "frequency_penalty",
        "max_tokens", "tools", "tool_choice",
    },
    "OpenAIAdapter": {
        "temperature", "presence_penalty", "frequency_penalty",
        "max_tokens", "tools", "tool_choice",
    },
    "ClaudeAdapter": {"temperature", "max_tokens"},
}


def filter_supported_chat_params(adapter_name: str, kwargs: dict) -> dict:
    supported = SUPPORTED_CHAT_PARAMS.get(adapter_name, set())
    return {k: v for k, v in kwargs.items() if k in supported}


class StreamingOpenAIMixin:
    def generate_stream(self, messages, *, tools=None, generation_config=None, on_text):
        from llm.streaming import generate_openai_stream
        return generate_openai_stream(self, messages, tools=tools,
                                      generation_config=generation_config, on_text=on_text)


def _create_openai_client(**kwargs):
    from openai import OpenAI
    return OpenAI(**kwargs)


class LazyOpenAIClientMixin:
    """Load the SDK on first use in a worker, rather than before the first frame."""

    def _configure_client(self, api_key, base_url):
        self._client = None
        self._client_lock = Lock()
        self._client_kwargs = {"api_key": api_key or "***", "base_url": base_url}

    @property
    def client(self):
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = _create_openai_client(**self._client_kwargs)
        return self._client

    @client.setter
    def client(self, value):
        with self._client_lock:
            self._client = value

    def client_settings(self):
        client = self._client
        if client is None:
            return dict(self._client_kwargs)
        return {"api_key": client.api_key, "base_url": client.base_url}

    def close(self):
        with self._client_lock:
            client = self._client
        if client is not None:
            client.close()


class OpenAICompatibleAdapter(LazyOpenAIClientMixin, StreamingOpenAIMixin, LLMAdapter):
    """通用 OpenAI 兼容接口，支持自定义服务地址与模型。"""

    def __init__(self, api_key=None, base_url=None, model="", **kwargs):
        super().__init__(**kwargs)
        self._configure_client(api_key, base_url)
        self.model = model

    def chat(self, messages: list, stream: bool = False, **kwargs):
        kwargs = filter_supported_chat_params("OpenAIAdapter", kwargs)
        params = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            **kwargs,
        }
        # 仅当 prompt 中包含 json 时启用 json_object 格式
        if any("json" in m.get("content", "").lower() for m in messages):
            params["response_format"] = {"type": "json_object"}
        return self.client.chat.completions.create(**params)


class DeepSeekAdapter(LazyOpenAIClientMixin, StreamingOpenAIMixin, LLMAdapter):
    """DeepSeek OpenAI 兼容接口"""

    def __init__(self, api_key=None, base_url=None, model="deepseek-chat", **kwargs):
        super().__init__(**kwargs)
        self._configure_client(api_key, base_url)
        self.model = model

    @staticmethod
    def _messages_include_tool_result(messages: list) -> bool:
        return any(message.get("role") == "tool" for message in messages)

    def generate(self, messages: list, *, tools=None, generation_config=None):
        params = dict(generation_config or {})
        if tools is not None:
            params["tools"] = tools
        if not tools or self._messages_include_tool_result(messages):
            params["response_format"] = {"type": "json_object"}
        else:
            params["_suppress_json_mode"] = True
        return self.chat(messages=messages, stream=False, **params)

    def chat(self, messages: list, stream: bool = False, **kwargs):
        response_format = kwargs.pop("response_format", None)
        suppress_json_mode = kwargs.pop("_suppress_json_mode", False)
        kwargs = filter_supported_chat_params("DeepSeekAdapter", kwargs)
        params = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            **kwargs,
        }
        if response_format is not None:
            params["response_format"] = response_format
        elif not suppress_json_mode and any("json" in m.get("content", "").lower() for m in messages):
            params["response_format"] = {"type": "json_object"}
        return self.client.chat.completions.create(**params)


class OpenAIAdapter(LazyOpenAIClientMixin, StreamingOpenAIMixin, LLMAdapter):
    """OpenAI / OpenAI 兼容端点"""

    def __init__(self, api_key=None, base_url=None, model="gpt-4o", **kwargs):
        super().__init__(**kwargs)
        self._configure_client(api_key, base_url)
        self.model = model

    def chat(self, messages: list, stream: bool = False, **kwargs):
        kwargs = filter_supported_chat_params("OpenAIAdapter", kwargs)
        params = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            **kwargs,
        }
        if any("json" in m.get("content", "").lower() for m in messages):
            params["response_format"] = {"type": "json_object"}
        return self.client.chat.completions.create(**params)


class ClaudeAdapter(LLMAdapter):
    """Anthropic Claude 适配器"""

    def generate_stream(self, messages, *, tools=None, generation_config=None, on_text):
        from llm.streaming import generate_claude_stream
        return generate_claude_stream(self, messages, tools=tools,
                                     generation_config=generation_config, on_text=on_text)

    def __init__(self, api_key=None, base_url=None, model="claude-sonnet-4-20250514", **kwargs):
        super().__init__(**kwargs)
        try:
            from anthropic import Anthropic
            self.client = Anthropic(api_key=api_key)
        except ImportError:
            raise ImportError("请安装 anthropic: pip install anthropic")
        self.model = model

    def chat(self, messages: list, stream: bool = False, **kwargs):
        kwargs = filter_supported_chat_params("ClaudeAdapter", kwargs)
        # 分离 system message
        system_msg = ""
        chat_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_msg = msg.get("content", "")
            else:
                chat_messages.append(msg)

        params = {
            "model": self.model,
            "messages": chat_messages,
            "max_tokens": kwargs.pop("max_tokens", 4096),
        }
        if system_msg:
            params["system"] = system_msg
        if kwargs.get("temperature"):
            params["temperature"] = kwargs["temperature"]

        if stream:
            return self.client.messages.stream(**params)
        response = self.client.messages.create(**params)
        return response


class LLMAdapterFactory:
    """LLM 适配器工厂"""

    _adapters = {
        "deepseek": DeepSeekAdapter,
        "openai": OpenAIAdapter,
        "claude": ClaudeAdapter,
        "openai_compatible": OpenAICompatibleAdapter,
        "custom": OpenAICompatibleAdapter,
        "aipaibox": OpenAICompatibleAdapter,
    }

    @classmethod
    def register(cls, name: str, adapter_cls):
        cls._adapters[name.lower()] = adapter_cls

    @classmethod
    def create_adapter(cls, llm_provider: str = "deepseek", **kwargs) -> LLMAdapter:
        provider = llm_provider.lower().strip()
        # 精确匹配
        adapter_cls = cls._adapters.get(provider)
        if adapter_cls is None:
            # 模糊匹配
            for key, val in cls._adapters.items():
                if key in provider or provider in key:
                    adapter_cls = val
                    break
        if adapter_cls is None:
            # 默认使用通用 OpenAI 兼容适配器
            adapter_cls = OpenAICompatibleAdapter
        return adapter_cls(**kwargs)
