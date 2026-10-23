import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.settings_ui.web_tab import build_web_tab


def test_free_web_settings_tab_is_zero_key_and_exposes_runtime_controls() -> None:
    app = QApplication.instance() or QApplication([])
    parts = build_web_tab(object())

    assert parts.enabled_check.text() == "启用免费联网搜索（DDGS）"
    assert parts.region_combo.currentData() == "cn-zh"
    assert parts.safesearch_combo.currentData() == "moderate"
    assert parts.max_results_spin.value() == 5
    assert parts.timeout_spin.value() == 15
    assert parts.max_chars_spin.value() == 12000
    assert "API Key" in parts.hint_label.text()
    assert not parts.widget.findChildren(type(parts.hint_label), "api_key_input")

    parts.widget.close()
    assert app is not None
