"""文本处理器：解析 LLM 输出中的情绪标签、对话内容等。"""
import json
import re
from typing import Dict, Optional, Tuple


class TextProcessor:
    """解析 LLM 回复中的结构化内容（情绪、对话文本、动作等）"""

    # 匹配 JSON 格式的回复
    JSON_PATTERN = re.compile(r"\{[^{}]*\}", re.DOTALL)

    def parse_response(self, text: str) -> Dict[str, str]:
        """
        解析 LLM 回复，提取结构化字段。
        期望格式: {"emotion": "happy", "text": "你好呀！", "action": "微笑"}
        """
        result = {
            "emotion": "neutral",
            "text": text,
            "action": "",
        }

        # 尝试 JSON 解析
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                result["emotion"] = data.get("emotion", "neutral")
                result["text"] = data.get("text", data.get("content", text))
                result["action"] = data.get("action", "")
                return result
        except (json.JSONDecodeError, TypeError):
            pass

        # 尝试从文本中提取 JSON 块
        match = self.JSON_PATTERN.search(text)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, dict):
                    result["emotion"] = data.get("emotion", "neutral")
                    result["text"] = data.get("text", data.get("content", text))
                    result["action"] = data.get("action", "")
                    return result
            except (json.JSONDecodeError, TypeError):
                pass

        # 尝试匹配 [emotion] 标签格式
        emotion_match = re.match(r"\[([\w]+)\]\s*(.*)", text, re.DOTALL)
        if emotion_match:
            result["emotion"] = emotion_match.group(1)
            result["text"] = emotion_match.group(2).strip()

        return result

    def extract_emotion(self, text: str) -> str:
        """仅提取情绪标签"""
        parsed = self.parse_response(text)
        return parsed["emotion"]

    def extract_dialogue(self, text: str) -> str:
        """仅提取对话文本"""
        parsed = self.parse_response(text)
        return parsed["text"]
