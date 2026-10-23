from types import SimpleNamespace

from llm.llm_adapter import DeepSeekAdapter


class FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[])


def _adapter_with_fake_client() -> tuple[DeepSeekAdapter, FakeCompletions]:
    adapter = DeepSeekAdapter(api_key="test", model="deepseek-test")
    completions = FakeCompletions()
    adapter.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return adapter, completions


def test_deepseek_generate_does_not_force_json_mode_before_tool_call() -> None:
    adapter, completions = _adapter_with_fake_client()
    messages = [
        {"role": "system", "content": "Reply using JSON objects."},
        {"role": "user", "content": "Read a file."},
    ]
    tools = [{"type": "function", "function": {"name": "read_file"}}]

    adapter.generate(
        messages,
        tools=tools,
        generation_config={"temperature": 0.4, "max_tokens": 321},
    )

    request = completions.calls[0]
    assert request["tools"] == tools
    assert request["temperature"] == 0.4
    assert request["max_tokens"] == 321
    assert "generation_config" not in request
    assert "response_format" not in request


def test_deepseek_generate_restores_json_mode_after_tool_result() -> None:
    adapter, completions = _adapter_with_fake_client()
    messages = [
        {"role": "system", "content": "Reply using JSON objects."},
        {"role": "assistant", "content": "", "tool_calls": []},
        {"role": "tool", "tool_call_id": "call-1", "content": "file content"},
    ]

    adapter.generate(messages, tools=[{"type": "function", "function": {"name": "read_file"}}])

    assert completions.calls[0]["response_format"] == {"type": "json_object"}


def test_deepseek_generate_without_tools_keeps_existing_json_behavior() -> None:
    adapter, completions = _adapter_with_fake_client()

    adapter.generate(
        [{"role": "system", "content": "Reply using JSON objects."}],
        tools=None,
    )

    assert completions.calls[0]["response_format"] == {"type": "json_object"}
