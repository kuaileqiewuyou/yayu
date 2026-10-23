"""CARD 资料卡：token、路由、TTS 拦截、持久化恢复、提示词与 UI。"""

from __future__ import annotations

from queue import Queue
from types import SimpleNamespace

import pytest

from core.handlers.tts_handlers import CardTtsHandler, get_tts_handlers
from core.messaging.dialog_tokens import CARD, is_system_token, match_card, normalize_name
from core.messaging.stream_parser import LlmResponseStreamParser
from core.messaging.template_output_validator import validate_template_output
from core.runtime.app_runtime import AppRuntime, clear_app_runtime, set_app_runtime
from core.runtime.chat_display import restore_chat_history_to_window
from core.runtime.llm_ui_handlers import LLMUiHandlers
from core.runtime.ui_message_router import route_llm_dialog, route_tts_output
from sdk.messages import LLMDialogMessage, TTSOutputMessage
from ui.chat_ui.info_card import is_safe_external_url

MARKDOWN = "## 结论\n- 要点一\n\n## 来源\n- [示例](https://example.com)"


# --- token -----------------------------------------------------------------

@pytest.mark.parametrize("name", ["CARD", "card", "Card", "INFO", "卡片"])
def test_card_aliases_match(name):
    assert match_card(name)
    assert is_system_token(name)


def test_card_normalizes_to_canonical_name():
    assert normalize_name("card") == CARD
    assert normalize_name("info") == CARD


def test_character_names_are_not_cards():
    assert not match_card("诺艾尔")


# --- parser ----------------------------------------------------------------

def test_stream_parser_accepts_raw_newlines_inside_card_markdown():
    raw = (
        '{"character_name": "诺艾尔", "speech": "查到啦", "sprite": "2"}\n'
        '{"character_name": "CARD", "speech": "## 结论\n- a {x}\n- b", "sprite": "-1"}\n'
    )
    parser = LlmResponseStreamParser()
    messages = []
    for i in range(0, len(raw), 7):
        messages.extend(parser.feed(raw[i:i + 7]))

    assert [(m.name, m.text) for m in messages] == [
        ("诺艾尔", "查到啦"),
        ("CARD", "## 结论\n- a {x}\n- b"),
    ]
    assert parser.parse_failures == 0


# --- routing ---------------------------------------------------------------

def test_route_llm_dialog_shows_card_immediately():
    msg = LLMDialogMessage(name="CARD", text=MARKDOWN, asset_id="-1")

    events = route_llm_dialog(msg, active_character_name="诺艾尔")

    assert len(events) == 1
    assert events[0].kind == "card"
    assert events[0].payload == MARKDOWN


def test_route_tts_output_does_not_duplicate_card():
    out = TTSOutputMessage(name="CARD", text=MARKDOWN, asset_id="-1")

    assert route_tts_output(out) == []


# --- TTS -------------------------------------------------------------------

def test_card_handler_runs_before_default_character_handler():
    handlers = get_tts_handlers()
    card_index = next(i for i, h in enumerate(handlers) if isinstance(h, CardTtsHandler))
    msg = LLMDialogMessage(name="CARD", text=MARKDOWN, asset_id="-1")

    first_match = next(h for h in handlers if h.can_handle(msg))

    assert first_match is handlers[card_index]


def test_card_is_never_synthesized_or_queued():
    synthesize_calls = []
    audio_path_queue = Queue()
    set_app_runtime(AppRuntime(
        config=None,
        llm_manager=None,
        tts_manager=SimpleNamespace(synthesize=lambda *a, **k: synthesize_calls.append(a) or "x.wav"),
        audio_path_queue=audio_path_queue,
    ))
    try:
        CardTtsHandler().handle(LLMDialogMessage(name="CARD", text=MARKDOWN, asset_id="-1"))
    finally:
        clear_app_runtime()

    assert synthesize_calls == []
    assert audio_path_queue.empty()


# --- LLM UI handler + persistence ------------------------------------------

class FakeWindow:
    def __init__(self):
        self.messages = []
        self.cards = []

    def add_message(self, text, is_user=False, char_name="", char_color="#f2a0bd"):
        self.messages.append({"text": text, "is_user": is_user, "char_name": char_name})

    def add_card(self, markdown, title="资料卡"):
        self.cards.append(markdown)

    def discard_stream(self):
        pass

    def end_stream(self):
        pass


class FakeHistory:
    def __init__(self):
        self.added = []

    def add_to_history(self, role, content, **kwargs):
        self.added.append({"role": role, "content": content, **kwargs})


def make_llm_handlers():
    window, history, sprites = FakeWindow(), FakeHistory(), []
    handlers = LLMUiHandlers(
        window=window, history=history, active_character_name="诺艾尔",
        char_color="#ABCDEF", set_sprite_by_id=sprites.append,
    )
    return handlers, window, history, sprites


def test_dialog_parsed_card_renders_card_and_persists_it():
    handlers, window, history, sprites = make_llm_handlers()

    handlers.on_dialog_parsed(LLMDialogMessage(name="CARD", text=MARKDOWN, asset_id="-1"))

    assert window.cards == [MARKDOWN]
    assert window.messages == []
    assert sprites == []
    assert history.added == [{"role": "assistant", "content": MARKDOWN, "name": "CARD", "kind": "card"}]


def test_dialog_parsed_blank_card_is_ignored():
    handlers, window, history, _ = make_llm_handlers()

    handlers.on_dialog_parsed(LLMDialogMessage(name="CARD", text="  \n", asset_id="-1"))

    assert window.cards == []
    assert history.added == []


def test_restore_chat_history_rebuilds_cards():
    window = FakeWindow()
    entries = [
        {"role": "user", "content": "帮我查一下"},
        {"role": "assistant", "content": "查到啦", "name": "诺艾尔"},
        {"role": "assistant", "content": MARKDOWN, "name": "CARD", "kind": "card"},
    ]

    restore_chat_history_to_window(window, entries)

    assert [m["text"] for m in window.messages] == ["帮我查一下", "查到啦"]
    assert window.cards == [MARKDOWN]


# --- prompt / validator ----------------------------------------------------

def test_prompt_documents_card_usage():
    from config.schema import Character
    from llm.template_generator import generate_system_prompt

    prompt = generate_system_prompt(Character(name="诺艾尔", character_setting="温柔可靠"))

    assert '"CARD" — 资料卡' in prompt
    assert "闲聊与剧情不要使用 CARD" in prompt
    card_examples = [line for line in prompt.splitlines() if line.startswith('{"character_name": "CARD"')]
    assert card_examples
    result = validate_template_output("\n".join(card_examples))
    assert result.is_valid
    assert not result.warnings


def test_validator_accepts_card_token_without_warning():
    line = '{"character_name": "CARD", "speech": "## 标题", "sprite": "-1"}'

    result = validate_template_output(line)

    assert result.is_valid
    assert not result.warnings


# --- link safety -----------------------------------------------------------

@pytest.mark.parametrize("url", ["https://example.com/a?b=1", "http://example.com"])
def test_safe_links_allowed(url):
    assert is_safe_external_url(url)


@pytest.mark.parametrize("url", [
    "file:///C:/Windows/System32/cmd.exe",
    "javascript:alert(1)",
    "ms-settings:privacy",
    "C:\\Windows\\notepad.exe",
    "https://",
    "",
])
def test_unsafe_links_blocked(url):
    assert not is_safe_external_url(url)


# --- summary ---------------------------------------------------------------

from ui.chat_ui.info_card import summarize_markdown  # noqa: E402


def test_summary_takes_first_heading_and_plain_preview_lines():
    title, lines = summarize_markdown("## 结论\n- **要点**一\n- 见 [文档](https://x.y)\n\n普通段落")

    assert title == "结论"
    assert lines == ["· 要点一", "· 见 文档", "普通段落"]


def test_summary_truncates_with_ellipsis():
    title, lines = summarize_markdown("- a\n- b\n- c\n- d", max_lines=3)

    assert title == ""
    assert lines == ["· a", "· b", "· c …"]


def test_summary_keeps_only_first_code_line():
    _, lines = summarize_markdown("```python\nprint(1)\nprint(2)\n```\n后文")

    assert lines == ["print(1)", "后文"]


def test_summary_of_empty_markdown():
    assert summarize_markdown("") == ("", [])
