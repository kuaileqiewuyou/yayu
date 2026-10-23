import ast
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from ui.settings_ui.system_tab import build_system_tab


@pytest.fixture
def qapp(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


class FakeSettingsWindow:
    pass


def test_system_tab_builder_exposes_existing_controls_and_options(qapp):
    owner = FakeSettingsWindow()

    parts = build_system_tab(owner)

    assert parts.widget.objectName() == "system_tab"
    assert parts.widget.accessibleName() == "System tab"
    assert parts.lang_combo.objectName() == "language_combo"
    assert parts.lang_combo.accessibleName() == "Interface language"
    assert [parts.lang_combo.itemText(i) for i in range(parts.lang_combo.count())] == ["zh_CN", "en", "ja"]
    assert parts.voice_lang_combo.objectName() == "voice_language_combo"
    assert parts.voice_lang_combo.accessibleName() == "Voice language"
    assert [parts.voice_lang_combo.itemText(i) for i in range(parts.voice_lang_combo.count())] == ["ja", "zh", "en"]
    assert parts.default_skills_edit.objectName() == "system_default_skills_input"
    assert parts.default_skills_edit.accessibleName() == "Global default skills"
    assert parts.default_skills_edit.placeholderText() == "例如：slice-of-life-pacing"
    assert parts.always_on_top_check.text() == "主界面始终置顶"
    assert parts.always_on_top_check.objectName() == "always_on_top_check"
    assert parts.always_on_top_check.accessibleName() == "Keep main window on top"
    assert parts.always_on_top_check.isChecked() is False


def test_settings_window_system_tab_method_delegates_to_builder_without_inline_widget_ownership():
    window_path = Path(__file__).resolve().parents[1] / "ui" / "settings_ui" / "window.py"
    source = window_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    settings_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SettingsWindow")
    method = next(
        node
        for node in settings_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "_create_system_tab"
    )
    method_source = ast.get_source_segment(source, method)

    assert "build_system_tab(self)" in method_source
    assert "self.lang_combo = self._system_tab_parts.lang_combo" in method_source
    assert "self.voice_lang_combo = self._system_tab_parts.voice_lang_combo" in method_source
    assert "self.system_default_skills_edit = self._system_tab_parts.default_skills_edit" in method_source
    assert "self.always_on_top_check = self._system_tab_parts.always_on_top_check" in method_source
    assert "QComboBox()" not in method_source
    assert "QLineEdit()" not in method_source
    assert "layout.addRow" not in method_source
