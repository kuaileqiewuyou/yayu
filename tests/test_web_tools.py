from types import SimpleNamespace

import httpx
import pytest

from config.schema import ApiConfig
from llm.tools.tool_manager import ToolManager
from llm.tools.web_tools import (
    FreeWebClient,
    FreeWebSettings,
    extract_readable_html,
    register_configured_web_tools,
    validate_public_http_url,
)


class _FakeSearchClient:
    def __init__(self):
        self.calls = []

    def text(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return [
            {"title": "Result A", "href": "https://example.com/a", "body": "Summary A"},
            {"title": "Result B", "url": "https://example.com/b", "description": "Summary B"},
        ]


def test_api_config_defaults_to_free_web_search_enabled() -> None:
    config = ApiConfig()

    assert config.web_search_enabled is True
    assert config.web_search_region == "cn-zh"
    assert config.web_search_safesearch == "moderate"
    assert config.web_search_max_results == 5


def test_web_tools_are_registered_only_when_enabled() -> None:
    disabled = ToolManager()
    enabled = ToolManager()

    register_configured_web_tools(disabled, ApiConfig(web_search_enabled=False))
    register_configured_web_tools(enabled, ApiConfig(web_search_enabled=True))

    assert "web_search" not in disabled.list_tools()
    assert {"web_search", "web_extract"} <= set(enabled.list_tools())


def test_free_search_normalizes_ddgs_results_and_honors_configured_cap() -> None:
    fake = _FakeSearchClient()
    settings = FreeWebSettings(enabled=True, max_results=2, region="cn-zh", safesearch="moderate")
    client = FreeWebClient(settings, search_client_factory=lambda: fake)

    result = client.search("today's news", max_results=10)

    assert result["result_count"] == 2
    assert result["results"][0] == {
        "title": "Result A",
        "url": "https://example.com/a",
        "snippet": "Summary A",
    }
    assert fake.calls == [
        (
            "today's news",
            {"region": "cn-zh", "safesearch": "moderate", "max_results": 2},
        )
    ]


def test_html_extraction_removes_script_and_collapses_layout_noise() -> None:
    title, text = extract_readable_html(
        "<html><head><title> Example </title><script>attack()</script></head>"
        "<body><main><h1>Hello</h1><p>Useful   text.</p></main></body></html>"
    )

    assert title == "Example"
    assert "Hello" in text
    assert "Useful text." in text
    assert "attack" not in text


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://127.0.0.1/admin",
        "http://10.0.0.1/private",
        "http://169.254.169.254/latest/meta-data",
    ],
)
def test_web_extract_blocks_non_public_targets(url: str) -> None:
    with pytest.raises(ValueError):
        validate_public_http_url(url)


def test_web_extract_returns_bounded_readable_content_from_public_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html><head><title>News</title></head><body><article>Verified story</article></body></html>",
            request=request,
        )

    client = FreeWebClient(
        FreeWebSettings(enabled=True, extract_max_chars=1000),
        http_transport=httpx.MockTransport(handler),
    )

    result = client.extract(["https://93.184.216.34/story"])

    assert result["page_count"] == 1
    assert result["pages"][0]["title"] == "News"
    assert result["pages"][0]["content"] == "News\nVerified story"
    assert result["pages"][0]["truncated"] is False


def test_free_web_settings_clamps_untrusted_runtime_values() -> None:
    settings = FreeWebSettings.from_api_config(
        SimpleNamespace(
            web_search_enabled=True,
            web_search_max_results=999,
            web_extract_timeout_seconds=1,
            web_extract_max_chars=999999,
        )
    )

    assert settings.enabled is True
    assert settings.max_results == 10
    assert settings.extract_timeout_seconds == 5
    assert settings.extract_max_chars == 50000


def test_search_site_filter_keeps_only_matching_domains() -> None:
    class Fake:
        def __init__(self):
            self.calls = []

        def text(self, query, **kwargs):
            self.calls.append((query, kwargs))
            return [
                {"title": "A", "href": "https://example.com/a", "body": "s1"},
                {"title": "B", "href": "https://sub.example.com/b", "body": "s2"},
                {"title": "C", "href": "https://other.org/c", "body": "s3"},
            ]

    fake = Fake()
    client = FreeWebClient(
        FreeWebSettings(enabled=True, max_results=10),
        search_client_factory=lambda: fake,
    )

    result = client.search("test", site="example.com")

    assert [r["url"] for r in result["results"]] == [
        "https://example.com/a",
        "https://sub.example.com/b",
    ]
    assert result["result_count"] == 2


def test_search_passes_region_and_time_range_per_call() -> None:
    fake = _FakeSearchClient()
    client = FreeWebClient(
        FreeWebSettings(enabled=True, max_results=2, region="cn-zh"),
        search_client_factory=lambda: fake,
    )

    client.search("news", region="us-en", time_range="week")

    assert fake.calls[0][1]["region"] == "us-en"
    assert fake.calls[0][1]["timelimit"] == "w"
    # 未传 time_range 时不带 timelimit 参数（保持向后兼容）
    client.search("plain")
    assert "timelimit" not in fake.calls[1][1]


def test_tool_quota_blocks_after_max_calls_and_resets() -> None:
    tm = ToolManager()
    tm.register("echo", lambda x: x)
    tm.set_tool_quota("echo", 2)

    assert tm.call_tool("echo", {"x": 1}).success is True
    assert tm.call_tool("echo", {"x": 2}).success is True
    blocked = tm.call_tool("echo", {"x": 3})
    assert blocked.success is False
    assert "配额上限" in blocked.error

    tm.reset_quotas()
    assert tm.call_tool("echo", {"x": 4}).success is True


def test_register_configured_web_tools_sets_quotas_from_config() -> None:
    tm = ToolManager()
    register_configured_web_tools(
        tm,
        ApiConfig(web_search_enabled=True, web_search_max_calls=2, web_extract_max_calls=1),
    )

    assert tm.get_tool_quota("web_search") == 2
    assert tm.get_tool_quota("web_extract") == 1


def test_web_extract_failure_includes_source_fallback_hint() -> None:
    tm = ToolManager()
    register_configured_web_tools(tm, ApiConfig(web_search_enabled=True))

    result = tm.call_tool("web_extract", {"urls": ["http://127.0.0.1/x", "https://example.com/y"]})

    assert result.success is False
    assert "请换用" in result.error
    assert "web_extract" in result.error
    # 错误消息必须指明是哪个 URL 失败，模型才能精确换源
    assert "http://127.0.0.1/x" in result.error
