"""Cancellable streaming transports for the built-in model adapters."""
from __future__ import annotations

import httpx
from openai import AsyncOpenAI

from core.runtime.cancellation import check_cancelled, run_async


async def collect_openai_stream(stream, on_text):
    content = []
    calls = {}
    finished = False
    try:
        async for chunk in stream:
            check_cancelled()
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            reason = getattr(chunk.choices[0], "finish_reason", None)
            if reason:
                if reason not in {"stop", "tool_calls"}:
                    raise RuntimeError(f"模型回复未完整结束（{reason}），请重试或调整输出长度。")
                finished = True
            for part in delta.tool_calls or []:
                call = calls.setdefault(part.index, {
                    "id": "", "type": "function", "function": {"name": "", "arguments": ""},
                })
                if part.id:
                    call["id"] += part.id
                if part.function:
                    call["function"]["name"] += part.function.name or ""
                    call["function"]["arguments"] += part.function.arguments or ""
            if delta.content:
                content.append(delta.content)
                if not calls:
                    on_text(delta.content)
    finally:
        await stream.close()
    if not finished:
        raise RuntimeError("模型连接提前结束，未收到完整回复。请重试。")
    return {"content": "".join(content), "tool_calls": [calls[i] for i in sorted(calls)]}


def generate_openai_stream(adapter, messages, *, tools, generation_config, on_text):
    from llm.llm_adapter import DeepSeekAdapter, filter_supported_chat_params
    params = filter_supported_chat_params("OpenAIAdapter", dict(generation_config or {}))
    if tools:
        params["tools"] = tools
    has_json = any("json" in str(m.get("content") or "").lower() for m in messages)
    if isinstance(adapter, DeepSeekAdapter):
        has_json = not tools or adapter._messages_include_tool_result(messages)
    if (generation_config or {}).get("_plain_text"):
        has_json = False
    if has_json:
        params["response_format"] = {"type": "json_object"}

    async def generate():
        get_settings = getattr(adapter, "client_settings", None)
        settings = get_settings() if callable(get_settings) else {
            "api_key": adapter.client.api_key, "base_url": adapter.client.base_url,
        }
        async with AsyncOpenAI(
            **settings,
            timeout=httpx.Timeout(60.0, connect=10.0), max_retries=0,
        ) as client:
            stream = await client.chat.completions.create(
                model=adapter.model, messages=messages, stream=True, **params,
            )
            return await collect_openai_stream(stream, on_text)

    return run_async(generate)


def generate_claude_stream(adapter, messages, *, tools, generation_config, on_text):
    from anthropic import AsyncAnthropic
    params = dict(generation_config or {})
    system = "\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")
    chat = [m for m in messages if m.get("role") != "system"]

    async def generate():
        async with AsyncAnthropic(
            api_key=adapter.client.api_key, base_url=adapter.client.base_url,
            timeout=httpx.Timeout(60.0, connect=10.0), max_retries=0,
        ) as client:
            chunks = []
            async with client.messages.stream(
                model=adapter.model, messages=chat, system=system,
                max_tokens=params.get("max_tokens", 4096), temperature=params.get("temperature", 0.7),
            ) as stream:
                async for text in stream.text_stream:
                    check_cancelled()
                    chunks.append(text)
                    on_text(text)
            return {"content": "".join(chunks), "tool_calls": []}

    return run_async(generate)
