"""LLM 管理器：管理对话历史、流式输出、工具调用。"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional

from llm.llm_adapter import LLMAdapter, LLMAdapterFactory

logger = logging.getLogger(__name__)


class LLMManager:
    """管理 LLM 对话流程"""

    def __init__(
        self,
        adapter: LLMAdapter,
        user_template: str = "",
        max_tokens: int = 128000,
        generation_config: Optional[Dict[str, Any]] = None,
    ):
        self.adapter = adapter
        self.user_template = user_template
        self.max_tokens = max_tokens
        self.generation_config = generation_config or {
            "temperature": 0.7,
            "max_tokens": 4096,
        }
        self._messages: List[Dict[str, str]] = []
        if user_template:
            self._messages.append({"role": "system", "content": user_template})

    def get_messages(self) -> List[Dict[str, str]]:
        return self._messages.copy()

    def get_generation_config(self) -> Dict[str, Any]:
        return dict(self.generation_config)

    def set_messages(self, messages: List[Dict[str, str]]):
        self._messages = messages

    def build_user_message(self, text: str) -> Dict[str, str]:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        content = f"[本地时间 {ts}]\n{text}"
        return {"role": "user", "content": content}

    def add_user_message(self, text: str) -> None:
        self._messages.append(self.build_user_message(text))

    def chat(self, user_input: str, stream: bool = True) -> Any:
        """发送用户消息并获取 LLM 回复"""
        self.add_user_message(user_input)

        response = self.adapter.chat(
            messages=self._messages,
            stream=stream,
            **self.generation_config,
        )

        if not stream:
            # 非流式：直接提取回复
            content = self._extract_content(response)
            self._messages.append({"role": "assistant", "content": content})
            return content
        else:
            return response  # 返回流式生成器

    def process_stream(self, stream_response) -> Generator[str, None, None]:
        """处理流式响应，逐块 yield 文本"""
        full_content = ""
        for chunk in stream_response:
            if hasattr(chunk, "choices") and chunk.choices:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    full_content += delta.content
                    yield delta.content
        # 流结束后保存完整回复
        if full_content:
            self._messages.append({"role": "assistant", "content": full_content})

    def _extract_content(self, response) -> str:
        """从非流式响应中提取文本"""
        if hasattr(response, "choices"):
            return response.choices[0].message.content or ""
        if hasattr(response, "content"):
            # Claude 格式
            blocks = response.content
            return "".join(b.text for b in blocks if hasattr(b, "text"))
        return str(response)

    def clear_history(self):
        """清空对话历史，保留 system prompt"""
        system_msgs = [m for m in self._messages if m["role"] == "system"]
        self._messages = system_msgs

    def set_template(self, template: str):
        """更新 system prompt"""
        self.user_template = template
        # 替换或添加 system message
        self._messages = [m for m in self._messages if m["role"] != "system"]
        if template:
            self._messages.insert(0, {"role": "system", "content": template})
