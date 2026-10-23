from __future__ import annotations

from dataclasses import dataclass
from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QCheckBox,
)

from ui.settings_ui.controls import NoWheelDoubleSpinBox, SafeComboBox
from ui.settings_ui.daylight import COLOR_DIM, icon
from ui.settings_ui.presentation import page_layout, card, ResponsiveFields, row_widget, hint


PROVIDERS = {
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "models": ["deepseek-chat", "deepseek-reasoner"]},
    "openai": {"base_url": "https://api.openai.com/v1", "models": ["gpt-4o", "gpt-4o-mini", "o1"]},
    "custom": {"base_url": "", "models": []},
    "claude": {"base_url": "https://api.anthropic.com/v1", "models": ["claude-opus-4-7", "claude-sonnet-4"]},
}


@dataclass
class APISettingsTabParts:
    widget: QWidget
    llm_provider_combo: SafeComboBox
    api_key_edit: QLineEdit
    base_url_edit: QLineEdit
    model_edit: QLineEdit
    llm_check_button: QPushButton
    temp_spin: NoWheelDoubleSpinBox
    stream_check: QCheckBox
    t2i_provider_combo: SafeComboBox
    t2i_api_url_edit: QLineEdit
    t2i_checkpoint_edit: QLineEdit
    t2i_check_button: QPushButton
    t2i_hint_label: QLabel
    llm_status_label: QLabel
    t2i_status_label: QLabel


def available_t2i_providers() -> list[str]:
    """Return T2I/CG providers selectable in settings."""
    return ["none", "comfyui"]


def build_api_tab(owner) -> APISettingsTabParts:
    widget = QWidget()
    widget.setObjectName("api_tab")
    widget.setAccessibleName("API settings tab")
    page = page_layout(widget, "模型配置", "配置对话模型与图像生成引擎，支持多种服务与本地部署。")
    llm_group, llm_layout = card("对话模型")
    image_group, image_layout = card("场景图像生成")

    llm_provider_combo = SafeComboBox()
    llm_provider_combo.setObjectName("llm_provider_combo")
    llm_provider_combo.setAccessibleName("LLM provider")
    for provider in PROVIDERS:
        llm_provider_combo.addItem("自定义" if provider == "custom" else provider, provider)
    llm_provider_combo.currentTextChanged.connect(owner._on_provider_changed)

    api_key_edit = QLineEdit()
    api_key_edit.setObjectName("api_key_input")
    api_key_edit.setAccessibleName("API key")
    api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
    reveal = api_key_edit.addAction(icon("eye"), QLineEdit.ActionPosition.TrailingPosition)
    reveal.setToolTip("显示 / 隐藏 API Key")
    reveal.setCheckable(True)
    reveal.toggled.connect(lambda checked: api_key_edit.setEchoMode(
        QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password))

    base_url_edit = QLineEdit()
    base_url_edit.setObjectName("base_url_input")
    base_url_edit.setAccessibleName("Base URL")
    base_url_edit.setPlaceholderText("例如：https://service.example/v1")

    model_edit = QLineEdit()
    model_edit.setObjectName("model_input")
    model_edit.setAccessibleName("Model ID")
    model_edit.setPlaceholderText("填写服务支持的完整模型 ID")

    llm_check_button = QPushButton("检查 LLM 配置")
    llm_check_button.setObjectName("llm_check_button")
    llm_check_button.setAccessibleName("Check LLM configuration")
    llm_check_button.clicked.connect(owner._check_llm_config)

    temp_spin = NoWheelDoubleSpinBox()
    temp_spin.setObjectName("temperature_spin")
    temp_spin.setAccessibleName("LLM temperature")
    temp_spin.setRange(0.0, 2.0)
    temp_spin.setSingleStep(0.1)

    stream_check = QCheckBox("启用流式输出")
    stream_check.setObjectName("stream_output_checkbox")
    stream_check.setAccessibleName("Enable streaming output")

    t2i_provider_combo = SafeComboBox()
    t2i_provider_combo.setObjectName("t2i_provider_combo")
    t2i_provider_combo.setAccessibleName("T2I provider")
    t2i_provider_combo.addItems(available_t2i_providers())
    t2i_provider_combo.currentTextChanged.connect(owner._update_t2i_provider_hint)

    t2i_api_url_edit = QLineEdit()
    t2i_api_url_edit.setObjectName("t2i_api_url_input")
    t2i_api_url_edit.setAccessibleName("ComfyUI API URL")
    t2i_api_url_edit.setPlaceholderText("例如：http://127.0.0.1:8188")

    t2i_checkpoint_edit = QLineEdit()
    t2i_checkpoint_edit.setObjectName("t2i_checkpoint_input")
    t2i_checkpoint_edit.setAccessibleName("ComfyUI checkpoint")
    t2i_checkpoint_edit.setPlaceholderText("例如：v1-5-pruned-emaonly.ckpt")

    t2i_check_button = QPushButton("测试 ComfyUI 连接")
    t2i_check_button.setObjectName("t2i_check_button")
    t2i_check_button.setAccessibleName("Test ComfyUI connection")
    t2i_check_button.clicked.connect(owner._check_comfyui_connection)

    t2i_hint_label = QLabel("")
    t2i_hint_label.setWordWrap(True)
    t2i_hint_label.setProperty("role", "muted")
    temp_spin.setFixedWidth(145)
    llm_status_label = hint("尚未检查")
    t2i_status_label = hint("尚未检测")

    llm_layout.addWidget(ResponsiveFields([
        ("模型提供方", llm_provider_combo), ("模型 ID", model_edit),
        ("API Key", api_key_edit), ("Temperature", row_widget([temp_spin, hint("0.0 – 2.0")], stretch=True)),
        ("Base URL", base_url_edit), ("输出方式", stream_check),
    ]))
    llm_layout.addWidget(hint("选择“自定义”可填写 OpenAI 兼容服务的接口地址、模型 ID 和 API Key。"))
    llm_check_button.setProperty("role", "primary")
    llm_layout.addWidget(row_widget([llm_check_button, llm_status_label], stretch=True))
    image_layout.addWidget(ResponsiveFields([
        ("T2I / CG 引擎", t2i_provider_combo), ("ComfyUI API URL", t2i_api_url_edit),
        ("", t2i_hint_label), ("ComfyUI Checkpoint", t2i_checkpoint_edit),
    ]))
    image_layout.addWidget(row_widget([t2i_check_button, t2i_status_label], stretch=True))
    page.addWidget(llm_group)
    page.addWidget(image_group)
    page.addStretch()

    return APISettingsTabParts(
        widget=widget,
        llm_provider_combo=llm_provider_combo,
        api_key_edit=api_key_edit,
        base_url_edit=base_url_edit,
        model_edit=model_edit,
        llm_check_button=llm_check_button,
        temp_spin=temp_spin,
        stream_check=stream_check,
        t2i_provider_combo=t2i_provider_combo,
        t2i_api_url_edit=t2i_api_url_edit,
        t2i_checkpoint_edit=t2i_checkpoint_edit,
        t2i_check_button=t2i_check_button,
        t2i_hint_label=t2i_hint_label,
        llm_status_label=llm_status_label,
        t2i_status_label=t2i_status_label,
    )
