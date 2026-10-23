import ast
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QLineEdit

from ui.settings_ui.daylight import COLOR_DIM
from ui.settings_ui.api_tab import PROVIDERS, available_t2i_providers, build_api_tab


@pytest.fixture
def qapp(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


class FakeSettingsWindow:
    def __init__(self):
        self.provider_updates = []
        self.t2i_hint_updates = []
        self.llm_checks = 0
        self.t2i_checks = 0

    def _on_provider_changed(self, provider: str):
        self.provider_updates.append(provider)

    def _check_llm_config(self):
        self.llm_checks += 1

    def _update_t2i_provider_hint(self, provider: str):
        self.t2i_hint_updates.append(provider)

    def _check_comfyui_connection(self):
        self.t2i_checks += 1


def test_api_tab_builder_exposes_existing_llm_and_t2i_controls(qapp):
    owner = FakeSettingsWindow()

    parts = build_api_tab(owner)

    assert parts.widget.objectName() == "api_tab"
    assert parts.widget.accessibleName() == "API settings tab"
    assert parts.llm_provider_combo.objectName() == "llm_provider_combo"
    assert parts.llm_provider_combo.accessibleName() == "LLM provider"
    assert [parts.llm_provider_combo.itemData(i) for i in range(parts.llm_provider_combo.count())] == list(PROVIDERS.keys())
    assert parts.llm_provider_combo.findText("自定义") >= 0
    assert parts.llm_provider_combo.findText("aipaibox") == -1
    assert parts.api_key_edit.objectName() == "api_key_input"
    assert parts.api_key_edit.accessibleName() == "API key"
    assert parts.api_key_edit.echoMode() == QLineEdit.EchoMode.Password
    assert parts.base_url_edit.objectName() == "base_url_input"
    assert parts.base_url_edit.accessibleName() == "Base URL"
    assert parts.model_edit.objectName() == "model_input"
    assert parts.model_edit.accessibleName() == "Model ID"
    assert parts.llm_check_button.objectName() == "llm_check_button"
    assert parts.llm_check_button.accessibleName() == "Check LLM configuration"
    assert parts.llm_check_button.text() == "检查 LLM 配置"
    assert parts.temp_spin.objectName() == "temperature_spin"
    assert parts.temp_spin.accessibleName() == "LLM temperature"
    assert parts.temp_spin.minimum() == pytest.approx(0.0)
    assert parts.temp_spin.maximum() == pytest.approx(2.0)
    assert parts.temp_spin.singleStep() == pytest.approx(0.1)
    assert parts.stream_check.objectName() == "stream_output_checkbox"
    assert parts.stream_check.accessibleName() == "Enable streaming output"
    assert parts.t2i_provider_combo.objectName() == "t2i_provider_combo"
    assert parts.t2i_provider_combo.accessibleName() == "T2I provider"
    assert [parts.t2i_provider_combo.itemText(i) for i in range(parts.t2i_provider_combo.count())] == ["none", "comfyui"]
    assert available_t2i_providers() == ["none", "comfyui"]
    assert parts.t2i_api_url_edit.objectName() == "t2i_api_url_input"
    assert parts.t2i_api_url_edit.accessibleName() == "ComfyUI API URL"
    assert parts.t2i_api_url_edit.placeholderText() == "例如：http://127.0.0.1:8188"
    assert parts.t2i_checkpoint_edit.objectName() == "t2i_checkpoint_input"
    assert parts.t2i_checkpoint_edit.accessibleName() == "ComfyUI checkpoint"
    assert parts.t2i_checkpoint_edit.placeholderText() == "例如：v1-5-pruned-emaonly.ckpt"
    assert parts.t2i_check_button.objectName() == "t2i_check_button"
    assert parts.t2i_check_button.accessibleName() == "Test ComfyUI connection"
    assert parts.t2i_hint_label.wordWrap() is True
    assert parts.t2i_hint_label.property("role") == "muted"

    parts.llm_provider_combo.setCurrentText("openai")
    parts.t2i_provider_combo.setCurrentText("comfyui")
    parts.llm_check_button.click()
    parts.t2i_check_button.click()
    qapp.processEvents()

    assert owner.provider_updates[-1] == "openai"
    assert owner.t2i_hint_updates[-1] == "comfyui"
    assert owner.llm_checks == 1
    assert owner.t2i_checks == 1


def test_settings_window_api_tab_compatibility_forwarders_match_extracted_module():
    import ui.settings_ui.window as settings_window_module

    assert settings_window_module.PROVIDERS == PROVIDERS
    assert settings_window_module.available_t2i_providers() == available_t2i_providers()


def test_settings_window_api_tab_method_delegates_to_builder_without_inline_widget_ownership():
    window_path = Path(__file__).resolve().parents[1] / "ui" / "settings_ui" / "window.py"
    source = window_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    settings_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SettingsWindow")
    method = next(
        node
        for node in settings_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "_create_api_tab"
    )
    method_source = ast.get_source_segment(source, method)

    assert "build_api_tab(self)" in method_source
    assert "self.llm_provider_combo = self._api_tab_parts.llm_provider_combo" in method_source
    assert "self.api_key_edit = self._api_tab_parts.api_key_edit" in method_source
    assert "self.t2i_provider_combo = self._api_tab_parts.t2i_provider_combo" in method_source
    assert "self.t2i_hint_label = self._api_tab_parts.t2i_hint_label" in method_source
    assert "PROVIDERS.keys()" not in method_source
    assert "available_t2i_providers()" not in method_source
    assert "QDoubleSpinBox()" not in method_source
    assert "QLineEdit()" not in method_source
    assert "layout.addRow" not in method_source
