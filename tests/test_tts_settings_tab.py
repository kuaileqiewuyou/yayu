import ast
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from tts.tts_adapter import TTSAdapterFactory
from ui.settings_ui.daylight import COLOR_DIM
from ui.settings_ui.tts_tab import build_tts_tab, available_tts_providers


@pytest.fixture
def qapp(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


class FakeSettingsWindow:
    def __init__(self):
        self.hint_updates = []

    def _update_tts_provider_hint(self, provider: str):
        self.hint_updates.append(provider)


def test_tts_tab_builder_exposes_existing_controls_and_runtime_provider_options(qapp):
    owner = FakeSettingsWindow()

    parts = build_tts_tab(owner)

    assert parts.widget.objectName() == "tts_tab"
    assert parts.widget.accessibleName() == "TTS tab"
    assert parts.provider_combo.objectName() == "tts_provider_combo"
    assert parts.provider_combo.accessibleName() == "TTS provider"
    assert [parts.provider_combo.itemText(i) for i in range(parts.provider_combo.count())] == [
        "none",
        *sorted(TTSAdapterFactory._registry),
    ]
    assert available_tts_providers() == ["none", *sorted(TTSAdapterFactory._registry)]
    assert parts.url_edit.objectName() == "tts_url_input"
    assert parts.url_edit.accessibleName() == "TTS service URL"
    assert parts.voice_edit.objectName() == "tts_voice_input"
    assert parts.voice_edit.accessibleName() == "TTS voice"
    assert parts.voice_edit.placeholderText() == "例如：zh-CN-XiaoyiNeural / ja-JP-NanamiNeural"
    assert parts.speed_spin.objectName() == "tts_speed_spin"
    assert parts.speed_spin.accessibleName() == "TTS speed"
    assert parts.speed_spin.minimum() == pytest.approx(0.25)
    assert parts.speed_spin.maximum() == pytest.approx(3.0)
    assert parts.speed_spin.singleStep() == pytest.approx(0.05)
    assert parts.speed_spin.decimals() == 2
    assert parts.hint_label.wordWrap() is True
    assert parts.hint_label.property("role") == "notice"


def test_settings_window_tts_tab_method_delegates_to_builder_without_inline_widget_ownership():
    window_path = Path(__file__).resolve().parents[1] / "ui" / "settings_ui" / "window.py"
    source = window_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    settings_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SettingsWindow")
    method = next(
        node
        for node in settings_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "_create_tts_tab"
    )
    method_source = ast.get_source_segment(source, method)

    assert "build_tts_tab(self)" in method_source
    assert "self.tts_provider_combo = self._tts_tab_parts.provider_combo" in method_source
    assert "available_tts_providers()" not in method_source
    assert "QDoubleSpinBox()" not in method_source
    assert "QLineEdit()" not in method_source
    assert "QLabel(\"\")" not in method_source
