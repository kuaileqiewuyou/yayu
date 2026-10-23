"""Free web-search settings tab."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QCheckBox, QFormLayout, QLabel, QWidget

from ui.settings_ui.controls import NoWheelSpinBox, SafeComboBox
from ui.settings_ui.daylight import COLOR_DIM
from ui.settings_ui.presentation import page_layout, card, ResponsiveFields


@dataclass
class WebSettingsTabParts:
    widget: QWidget
    enabled_check: QCheckBox
    region_combo: SafeComboBox
    safesearch_combo: SafeComboBox
    max_results_spin: NoWheelSpinBox
    timeout_spin: NoWheelSpinBox
    max_chars_spin: NoWheelSpinBox
    hint_label: QLabel


def _add_option(combo: SafeComboBox, label: str, value: str) -> None:
    combo.addItem(label, value)


def build_web_tab(owner) -> WebSettingsTabParts:
    widget = QWidget()
    widget.setObjectName("web_search_tab")
    widget.setAccessibleName("Free web search settings tab")
    page = page_layout(widget, "联网搜索", "为角色提供搜索与网页阅读能力。")
    group, content = card("搜索偏好")
    read_group, read_content = card("网页读取")

    enabled_check = QCheckBox("启用免费联网搜索（DDGS）")
    enabled_check.setObjectName("web_search_enabled_checkbox")
    enabled_check.setAccessibleName("Enable free web search")
    page.addWidget(enabled_check)
    page.addWidget(group)
    page.addWidget(read_group)

    region_combo = SafeComboBox()
    region_combo.setObjectName("web_search_region_combo")
    region_combo.setAccessibleName("Web search region")
    _add_option(region_combo, "中国 / 中文", "cn-zh")
    _add_option(region_combo, "全球", "wt-wt")
    _add_option(region_combo, "美国 / 英文", "us-en")

    safesearch_combo = SafeComboBox()
    safesearch_combo.setObjectName("web_search_safesearch_combo")
    safesearch_combo.setAccessibleName("Web search safe search")
    _add_option(safesearch_combo, "中等", "moderate")
    _add_option(safesearch_combo, "严格", "on")
    _add_option(safesearch_combo, "关闭", "off")

    max_results_spin = NoWheelSpinBox()
    max_results_spin.setObjectName("web_search_max_results_spin")
    max_results_spin.setAccessibleName("Web search maximum results")
    max_results_spin.setRange(1, 10)
    max_results_spin.setValue(5)
    content.addWidget(ResponsiveFields([("搜索地区", region_combo), ("安全搜索", safesearch_combo), ("最大搜索结果", max_results_spin)], columns=3))

    timeout_spin = NoWheelSpinBox()
    timeout_spin.setObjectName("web_extract_timeout_spin")
    timeout_spin.setAccessibleName("Web extract timeout")
    timeout_spin.setRange(5, 60)
    timeout_spin.setSuffix(" 秒")
    timeout_spin.setValue(15)

    max_chars_spin = NoWheelSpinBox()
    max_chars_spin.setObjectName("web_extract_max_chars_spin")
    max_chars_spin.setAccessibleName("Web extract maximum characters")
    max_chars_spin.setRange(1000, 50000)
    max_chars_spin.setSingleStep(1000)
    max_chars_spin.setValue(12000)
    read_content.addWidget(ResponsiveFields([("网页读取超时", timeout_spin), ("单页正文上限", max_chars_spin)]))

    hint_label = QLabel(
        "完全免费且不需要 API Key。开启后，模型可以调用 web_search 搜索，再用 web_extract 读取网页正文。"
        "保存配置并重启应用后生效；DDGS 可能偶尔受到搜索站点限流。"
    )
    hint_label.setObjectName("web_search_hint_label")
    hint_label.setAccessibleName("Free web search hint")
    hint_label.setWordWrap(True)
    hint_label.setProperty("role", "notice")
    page.addWidget(hint_label)
    page.addStretch()

    return WebSettingsTabParts(
        widget=widget,
        enabled_check=enabled_check,
        region_combo=region_combo,
        safesearch_combo=safesearch_combo,
        max_results_spin=max_results_spin,
        timeout_spin=timeout_spin,
        max_chars_spin=max_chars_spin,
        hint_label=hint_label,
    )
