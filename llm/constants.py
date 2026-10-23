"""LLM 相关常量"""

# 各供应商默认 Base URL
LLM_BASE_URLS = {
    "deepseek": "https://api.deepseek.com/v1",
    "openai": "https://api.openai.com/v1",
    "claude": "https://api.anthropic.com",
    "moonshot": "https://api.moonshot.cn/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "yi": "https://api.lingyiwanwu.com/v1",
}

# 默认情绪列表
DEFAULT_EMOTIONS = [
    "neutral", "happy", "sad", "angry", "surprised",
    "shy", "thinking", "excited", "disappointed", "scared",
]
