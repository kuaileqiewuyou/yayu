"""Real Qt checks for custom OpenAI-compatible endpoints and legacy settings."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import yaml
from PySide6.QtWidgets import QMessageBox

from config.config_manager import ConfigManager
from llm import llm_adapter
from test_settings_window import (
    make_settings_window,
    settings_config,
    set_valid_template_preflight,
)


@pytest.fixture
def custom_settings_environment(settings_config, make_settings_window, tmp_path, monkeypatch):
    """Keep window services and all six configuration paths in a temporary tree."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "app-data"))
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        QMessageBox, "critical", lambda parent, title, text, *args, **kwargs: messages.append(text)
    )

    def unexpected_network(*args, **kwargs):
        raise AssertionError("LLM settings must not initialize a client or perform network requests")

    monkeypatch.setattr(llm_adapter, "_create_openai_client", unexpected_network)
    monkeypatch.setattr("ui.settings_ui.api_controller.request.urlopen", unexpected_network)
    return settings_config, make_settings_window, messages


def _select_provider(window, provider: str) -> None:
    index = window.llm_provider_combo.findData(provider)
    assert index >= 0, f"Missing provider option: {provider}"
    window.llm_provider_combo.setCurrentIndex(index)


def _fields(window) -> tuple[str, str, str]:
    return window.base_url_edit.text(), window.model_edit.text(), window.api_key_edit.text()


def _fill_fields(window, base_url: str, model: str, api_key: str) -> None:
    window.base_url_edit.setText(base_url)
    window.model_edit.setText(model)
    window.api_key_edit.setText(api_key)


def test_provider_options_replace_aipaibox_with_labeled_custom(custom_settings_environment):
    write_config, make_window, _ = custom_settings_environment
    write_config()
    window = make_window()
    combo = window.llm_provider_combo

    assert [combo.itemData(index) for index in range(combo.count())] == [
        "deepseek", "openai", "custom", "claude",
    ]
    assert combo.itemText(combo.findData("custom")) == "自定义"
    assert all("aipai" not in combo.itemText(index).lower() for index in range(combo.count()))


@pytest.mark.parametrize(
    ("stored_provider", "selected_provider"),
    [("aipaibox", "custom"), ("OpenAI", "openai"), ("OpenRouter", "custom")],
)
def test_legacy_provider_load_preserves_original_fields_without_writing(
    custom_settings_environment, stored_provider, selected_provider
):
    write_config, make_window, _ = custom_settings_environment
    expected = ("https://gateway.example.test/custom/v1", "tenant/model:latest", "offline-legacy-key")
    paths = write_config(api={
        "llm_provider": stored_provider,
        "llm_base_url": expected[0],
        "llm_model": {stored_provider: expected[1]},
        "llm_api_key": {stored_provider: expected[2]},
    })
    original = paths["api"].read_bytes()

    window = make_window()

    assert window.llm_provider_combo.currentData() == selected_provider
    assert _fields(window) == expected
    assert paths["api"].read_bytes() == original
    assert not paths["api_local"].exists()
    assert not window._settings_dirty


@pytest.mark.parametrize("stored_provider", ["custom", "aipaibox", "OpenRouter"])
def test_custom_settings_save_to_local_overlay_and_survive_reopening(
    custom_settings_environment, stored_provider
):
    write_config, make_window, messages = custom_settings_environment
    paths = write_config(api={
        "llm_provider": stored_provider,
        "llm_base_url": "https://old.example.test/v1",
        "llm_model": {stored_provider: "old-model", "deepseek": "saved-deepseek-model"},
        "llm_api_key": {stored_provider: "old-offline-key", "deepseek": "saved-deepseek-key"},
    })
    original_base = paths["api"].read_bytes()
    window = make_window()
    _select_provider(window, "custom")
    _fill_fields(window, " https://my-gateway.example.test/llm/v1 ", " personal/model:v2 ", " offline-new-key ")
    set_valid_template_preflight(window)

    window._save_config()

    assert not messages
    assert paths["api_local"].is_file()
    saved = yaml.safe_load(paths["api_local"].read_text(encoding="utf-8"))
    expected = ("https://my-gateway.example.test/llm/v1", "personal/model:v2", "offline-new-key")
    assert saved["llm_provider"] == "custom"
    assert saved["llm_base_url"] == expected[0]
    assert saved["llm_model"]["custom"] == expected[1]
    assert saved["llm_api_key"]["custom"] == expected[2]
    assert saved["llm_model"]["deepseek"] == "saved-deepseek-model"
    assert saved["llm_api_key"]["deepseek"] == "saved-deepseek-key"
    assert "自定义" not in saved["llm_model"]
    assert "自定义" not in saved["llm_api_key"]
    assert paths["api"].read_bytes() == original_base

    ConfigManager.reset()
    reopened = make_window()
    assert reopened.llm_provider_combo.currentData() == "custom"
    assert _fields(reopened) == expected
    assert not reopened._settings_dirty
    assert reopened.config.get_llm_api_config() == ("custom", expected[1], expected[0], expected[2])
    reopened._check_llm_config()
    assert "配置看起来可用" in reopened.save_status_label.text()
    assert expected[2] not in reopened.save_status_label.text()


def test_switching_providers_preserves_custom_and_builtin_unsaved_drafts(custom_settings_environment):
    write_config, make_window, _ = custom_settings_environment
    original_fields = ("https://saved-openai.example.test/v1", "saved-model", "saved-key")
    paths = write_config(api={
        "llm_provider": "OpenAI",
        "llm_base_url": original_fields[0],
        "llm_model": {"OpenAI": original_fields[1]},
        "llm_api_key": {"OpenAI": original_fields[2]},
    })
    original_base = paths["api"].read_bytes()
    window = make_window()

    _select_provider(window, "custom")
    assert _fields(window) == ("", "", "")
    draft = ("https://draft.example.test/custom/v1", "arbitrary/model:dev", "draft-offline-key")
    _fill_fields(window, *draft)
    _select_provider(window, "openai")
    assert _fields(window) == original_fields
    builtin_draft = ("https://edited-openai.example.test/v1", "edited-openai-model", "edited-openai-key")
    _fill_fields(window, *builtin_draft)
    _select_provider(window, "custom")
    assert _fields(window) == draft
    _select_provider(window, "openai")
    assert _fields(window) == builtin_draft
    _select_provider(window, "custom")
    assert _fields(window) == draft
    assert paths["api"].read_bytes() == original_base
    assert not paths["api_local"].exists()


@pytest.mark.parametrize("provider", ["custom", " Custom ", "aipaibox"])
def test_custom_and_legacy_adapters_use_supplied_endpoint_without_initializing_client(monkeypatch, provider):
    def unexpected_client(**kwargs):
        raise AssertionError("Adapter construction and cleanup must remain offline")

    monkeypatch.setattr(llm_adapter, "_create_openai_client", unexpected_client)
    adapter = llm_adapter.LLMAdapterFactory.create_adapter(
        llm_provider=provider,
        api_key="offline-key",
        base_url="https://custom.example.test/nested/v1",
        model="tenant/arbitrary-model:v2",
    )

    assert isinstance(adapter, llm_adapter.OpenAICompatibleAdapter)
    assert adapter.model == "tenant/arbitrary-model:v2"
    assert adapter.client_settings() == {
        "api_key": "offline-key",
        "base_url": "https://custom.example.test/nested/v1",
    }
    assert adapter._client is None
    adapter.close()
    assert adapter._client is None
