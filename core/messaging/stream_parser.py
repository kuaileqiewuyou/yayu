"""从 LLM 流式输出中按 JSON 对象切分并解析为 LLMDialogMessage。"""

from __future__ import annotations

import json
import re
from typing import Iterator

from sdk.messages import LLMDialogMessage


_LEADING_FENCE_RE = re.compile(r"\s*```(?:json)?\s*", re.IGNORECASE)
_CLOSING_FENCE_RE = re.compile(r"\s*```\s*", re.IGNORECASE)


class LlmResponseStreamParser:
    """消费文本 chunk，解析一个或多个 JSON dialog 对象。"""

    def __init__(self) -> None:
        self._buffer = ""
        self.accumulated_text = ""
        self.parse_failures = 0
        self.last_error: str = ""
        # strict=False：允许字符串内出现裸换行/制表符。模型写多行 Markdown（如 CARD）
        # 时经常不转义换行，严格模式会把整条消息当作解析失败丢掉。
        self._decoder = json.JSONDecoder(strict=False)

    @property
    def has_errors(self) -> bool:
        return self.parse_failures > 0

    @property
    def unparsed_remainder(self) -> str:
        return self._buffer[:200].strip()

    def feed(self, chunk: str) -> Iterator[LLMDialogMessage]:
        """将新到达的文本并入缓冲区，逐条 yield 已完整的 JSON 消息。"""
        if chunk:
            self._buffer += chunk
            self.accumulated_text += chunk
        yield from self._drain()

    def _drain(self) -> Iterator[LLMDialogMessage]:
        """JSON-aware 地从缓冲区解析完整 JSON 值。

        使用 ``JSONDecoder.raw_decode`` 而不是扫描 ``}``，避免字符串里的花括号
        被误认为对象边界；未闭合对象/数组会留在 buffer 中等待下一次 feed。
        """
        while True:
            if not self._discard_leading_noise():
                return

            try:
                data, end = self._decoder.raw_decode(self._buffer)
            except json.JSONDecodeError as e:
                if self._looks_incomplete(e):
                    return

                self.parse_failures += 1
                self.last_error = f"JSON 解析失败: {self._buffer[:80]}"
                self._discard_invalid_json_prefix(e.pos)
                continue

            self._buffer = self._buffer[end:]
            yield from self._messages_from_json_value(data)

    def _messages_from_json_value(self, data: object) -> Iterator[LLMDialogMessage]:
        if isinstance(data, list):
            for item in data:
                yield from self._message_from_item(item)
            return

        yield from self._message_from_item(data)

    def _message_from_item(self, item: object) -> Iterator[LLMDialogMessage]:
        if not isinstance(item, dict):
            self.parse_failures += 1
            self.last_error = f"JSON 不是 dialog object: {type(item).__name__}"
            return

        try:
            yield LLMDialogMessage(**item)
        except Exception as e:
            self.parse_failures += 1
            self.last_error = str(e)[:200]

    def _discard_leading_noise(self) -> bool:
        """跳过空白/markdown fence/前导文本，并定位到下一个 JSON 起点。"""
        while True:
            original = self._buffer
            self._buffer = self._buffer.lstrip()
            self._buffer = _LEADING_FENCE_RE.sub("", self._buffer, count=1)
            self._buffer = _CLOSING_FENCE_RE.sub("", self._buffer, count=1)
            if self._buffer == original:
                break

        start_candidates = [pos for pos in (self._buffer.find("{"), self._buffer.find("[")) if pos != -1]
        if not start_candidates:
            self._buffer = ""
            return False

        start = min(start_candidates)
        if start > 0:
            self._buffer = self._buffer[start:]
        return True

    def _discard_invalid_json_prefix(self, error_pos: int) -> None:
        """丢弃当前无效 JSON 前缀，尽量保留后续可能的 JSON 值。"""
        search_from = max(error_pos + 1, 1)
        next_candidates = [
            pos for pos in (self._buffer.find("{", search_from), self._buffer.find("[", search_from)) if pos != -1
        ]
        self._buffer = self._buffer[min(next_candidates):] if next_candidates else ""

    def _looks_incomplete(self, error: json.JSONDecodeError) -> bool:
        """判断 JSONDecodeError 是否更像是流式数据尚未到齐。"""
        stripped = self._buffer.rstrip()
        if not stripped:
            return True

        if error.pos >= len(stripped):
            return True

        msg = error.msg.lower()
        if msg.startswith("unterminated string"):
            return True

        # raw_decode 对未闭合容器经常报在缓冲区末尾或接近末尾，例如：
        #   Expecting ',' delimiter: line 1 column N (char N-1)
        if error.pos >= len(stripped) - 1 and any(
            marker in msg
            for marker in (
                "expecting value",
                "expecting ',' delimiter",
                "expecting property name enclosed in double quotes",
                "expecting ':' delimiter",
            )
        ):
            return True

        return False
