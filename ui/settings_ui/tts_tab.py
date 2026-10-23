from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QWidget,
    QFormLayout,
    QLabel,
    QLineEdit,
)

from tts.tts_adapter import TTSAdapterFactory
from ui.settings_ui.controls import NoWheelDoubleSpinBox, SafeComboBox
from ui.settings_ui.daylight import COLOR_DIM
from ui.settings_ui.presentation import page_layout, card, row_widget, hint


@dataclass
class TTSSettingsTabParts:
    widget: QWidget
    provider_combo: SafeComboBox
    url_edit: QLineEdit
    voice_edit: QLineEdit
    speed_spin: NoWheelDoubleSpinBox
    hint_label: QLabel


def available_tts_providers() -> list[str]:
    """Return TTS providers selectable in settings."""
    return ["none", *sorted(TTSAdapterFactory._registry)]


def build_tts_tab(owner) -> TTSSettingsTabParts:
    widget = QWidget()
    widget.setObjectName("tts_tab")
    widget.setAccessibleName("TTS tab")
    page = page_layout(widget, "语音设置", "选择语音合成引擎，调整声音与播放语速。角色参考音频在角色管理中设置。")
    group, content = card("语音合成")
    layout = QFormLayout()
    layout.setSpacing(24)
    layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    content.addLayout(layout)
    page.addWidget(group)

    provider_combo = SafeComboBox()
    provider_combo.setObjectName("tts_provider_combo")
    provider_combo.setAccessibleName("TTS provider")
    provider_combo.addItems(available_tts_providers())
    provider_combo.currentTextChanged.connect(owner._update_tts_provider_hint)
    layout.addRow("TTS 引擎:", provider_combo)

    url_edit = QLineEdit()
    url_edit.setObjectName("tts_url_input")
    url_edit.setAccessibleName("TTS service URL")
    layout.addRow("TTS 服务 URL:", url_edit)

    voice_edit = QLineEdit()
    voice_edit.setObjectName("tts_voice_input")
    voice_edit.setAccessibleName("TTS voice")
    voice_edit.setPlaceholderText("例如：zh-CN-XiaoyiNeural / ja-JP-NanamiNeural")
    layout.addRow("Edge TTS Voice:", voice_edit)

    speed_spin = NoWheelDoubleSpinBox()
    speed_spin.setObjectName("tts_speed_spin")
    speed_spin.setAccessibleName("TTS speed")
    speed_spin.setRange(0.25, 3.0)
    speed_spin.setSingleStep(0.05)
    speed_spin.setDecimals(2)
    speed_spin.setFixedWidth(150)
    layout.addRow("播放语速:", row_widget([speed_spin, hint("0.25 – 3.00 倍速")], stretch=True))

    hint_label = QLabel("")
    hint_label.setWordWrap(True)
    hint_label.setProperty("role", "notice")
    page.addWidget(hint_label)
    page.addStretch()

    return TTSSettingsTabParts(
        widget=widget,
        provider_combo=provider_combo,
        url_edit=url_edit,
        voice_edit=voice_edit,
        speed_spin=speed_spin,
        hint_label=hint_label,
    )
