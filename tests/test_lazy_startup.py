from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import subprocess
import sys
from pathlib import Path

import pytest

from core.runtime.lazy_settings import LazySettingsWindow
from llm import llm_adapter


def test_settings_shutdown_and_status_updates_do_not_create_hidden_window():
    calls = []
    created = SimpleNamespace(
        memory_tab=object(),
        set_mcp_runtime_controller=lambda value: calls.append(("controller", value)),
        refresh_mcp_status=lambda value: calls.append(("status", value)),
        show=lambda: calls.append("show"),
        raise_=lambda: calls.append("raise"),
        activateWindow=lambda: calls.append("activate"),
        close=lambda: calls.append("close"),
    )
    def factory():
        calls.append("create")
        return created
    window = LazySettingsWindow(factory)
    window.set_mcp_runtime_controller("controller")
    window.refresh_mcp_status("old")
    window.refresh_mcp_status("latest")
    assert window.memory_tab is None
    assert window.close() is True
    assert calls == []

    window.show()
    window.raise_()
    window.activateWindow()
    window.show()
    assert calls == ["create", ("controller", "controller"), ("status", "latest"), "show", "raise", "activate", "show"]
    assert window.memory_tab is created.memory_tab
    window.refresh_mcp_status("updated")
    assert calls[-1] == ("status", "updated")
    window.close()
    assert calls[-1] == "close"


def test_failed_settings_construction_can_be_retried():
    calls = []
    def factory():
        calls.append(1)
        if len(calls) == 1:
            raise OSError("failed to load settings")
        return SimpleNamespace(show=lambda: None)
    window = LazySettingsWindow(factory)
    with pytest.raises(OSError):
        window.show()
    assert not window.is_created
    window.show()
    assert window.is_created


@pytest.mark.parametrize("adapter_class", [llm_adapter.OpenAIAdapter, llm_adapter.DeepSeekAdapter, llm_adapter.OpenAICompatibleAdapter])
def test_client_initializes_once_on_first_use_and_supports_override(monkeypatch, adapter_class):
    calls = []
    client = object()
    def factory(**kwargs):
        calls.append(kwargs)
        return client
    monkeypatch.setattr(llm_adapter, "_create_openai_client", factory)
    adapter = adapter_class(api_key="test-key", base_url="https://example.test/v1")
    assert calls == []
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: adapter.client, range(12)))
    assert all(result is client for result in results)
    assert calls == [{"api_key": "test-key", "base_url": "https://example.test/v1"}]
    replacement = object()
    adapter.client = replacement
    assert adapter.client is replacement
    assert len(calls) == 1


def test_fresh_chat_import_and_adapter_creation_skip_openai_and_settings_modules():
    source = """
import sys
import core.runtime.chat_app
from llm.llm_adapter import OpenAIAdapter
OpenAIAdapter(api_key='test')
assert 'openai' not in sys.modules
assert 'ui.settings_ui.window' not in sys.modules
"""
    result = subprocess.run([sys.executable, "-E", "-c", source], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_stream_settings_and_cleanup_do_not_construct_unused_sync_client(monkeypatch):
    def unexpected(**kwargs):
        raise AssertionError("sync client should not be created for stream configuration or cleanup")
    monkeypatch.setattr(llm_adapter, "_create_openai_client", unexpected)
    adapter = llm_adapter.OpenAIAdapter(api_key="test", base_url=None)
    assert adapter.client_settings() == {"api_key": "test", "base_url": None}
    adapter.close()
    assert adapter._client is None
