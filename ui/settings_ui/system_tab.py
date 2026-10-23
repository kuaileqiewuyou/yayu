from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget, QLineEdit, QPushButton, QLabel, QHBoxLayout, QCheckBox
from PySide6.QtCore import Qt

from ui.settings_ui.controls import SafeComboBox, NoWheelSpinBox
from ui.settings_ui.presentation import page_layout, card, ResponsiveFields, FlowLayout, hint
from ui.settings_ui.update_panel import UpdatePanel


@dataclass
class SystemSettingsTabParts:
    widget: QWidget
    lang_combo: SafeComboBox
    voice_lang_combo: SafeComboBox
    default_skills_edit: QLineEdit
    always_on_top_check: QCheckBox
    reduce_motion_check: QCheckBox
    typewriter_enabled_check: QCheckBox
    typewriter_cps_spin: NoWheelSpinBox
    update_panel: UpdatePanel


def build_system_tab(owner) -> SystemSettingsTabParts:
    widget = QWidget()
    widget.setObjectName("system_tab")
    widget.setAccessibleName("System tab")
    page = page_layout(widget, "系统设置", "调整界面语言与全局默认行为。")
    update_panel = UpdatePanel()
    page.addWidget(update_panel)
    group, content = card("语言设置")
    page.addWidget(group)

    lang_combo = SafeComboBox()
    lang_combo.setObjectName("language_combo")
    lang_combo.setAccessibleName("Interface language")
    lang_combo.addItems(["zh_CN", "en", "ja"])

    voice_lang_combo = SafeComboBox()
    voice_lang_combo.setObjectName("voice_language_combo")
    voice_lang_combo.setAccessibleName("Voice language")
    voice_lang_combo.addItems(["ja", "zh", "en"])
    content.addWidget(ResponsiveFields([("界面语言", lang_combo), ("默认语音语言", voice_lang_combo)]))
    content.addWidget(hint("选择界面显示与角色语音使用的默认语言。"))
    window_group, window_content = card("窗口行为")
    page.addWidget(window_group)
    always_on_top_check = QCheckBox("主界面始终置顶")
    always_on_top_check.setObjectName("always_on_top_check")
    always_on_top_check.setAccessibleName("Keep main window on top")
    window_content.addWidget(always_on_top_check)
    window_content.addWidget(hint("开启后，切换到其他应用时主界面仍显示在上方。"))
    motion_group, motion_content = card("界面动效")
    page.addWidget(motion_group)
    reduce_motion_check = QCheckBox("减少动效")
    reduce_motion_check.setObjectName("reduce_motion_check")
    reduce_motion_check.setAccessibleName("Reduce motion")
    motion_content.addWidget(reduce_motion_check)
    motion_content.addWidget(hint("关闭立绘浮动、跳动和界面过渡，台词直接显示全文。"))
    typewriter_enabled_check = QCheckBox("角色台词逐字显示")
    typewriter_enabled_check.setObjectName("typewriter_enabled_check")
    typewriter_enabled_check.setAccessibleName("Typewriter dialogue")
    motion_content.addWidget(typewriter_enabled_check)
    typewriter_cps_spin = NoWheelSpinBox()
    typewriter_cps_spin.setObjectName("typewriter_cps_spin")
    typewriter_cps_spin.setAccessibleName("Typewriter characters per second")
    typewriter_cps_spin.setRange(5, 200)
    typewriter_cps_spin.setValue(40)
    typewriter_cps_spin.setSuffix(" 字/秒")
    motion_content.addWidget(ResponsiveFields([("显示速度", typewriter_cps_spin)]))
    motion_content.addWidget(hint("点击台词可直接看全文；长台词最多在 4 秒内显示完。"))

    def sync_motion_controls(*_):
        typewriter_enabled_check.setEnabled(not reduce_motion_check.isChecked())
        typewriter_cps_spin.setEnabled(not reduce_motion_check.isChecked() and typewriter_enabled_check.isChecked())

    reduce_motion_check.toggled.connect(sync_motion_controls)
    typewriter_enabled_check.toggled.connect(sync_motion_controls)
    typewriter_enabled_check.setChecked(True)
    sync_motion_controls()
    skills_group, skills = card("全局默认 Skills")
    page.addWidget(skills_group)

    default_skills_edit = QLineEdit()
    default_skills_edit.setObjectName("system_default_skills_input")
    default_skills_edit.setAccessibleName("Global default skills")
    default_skills_edit.setPlaceholderText("例如：slice-of-life-pacing")
    default_skills_edit.setParent(skills_group)
    default_skills_edit.hide()
    default_skills_edit.setReadOnly(True)
    default_skills_edit.setToolTip("在 Skills 页面勾选全局默认技能，保存配置后生效。")
    manage_skills = QPushButton("前往 Skills 管理 →")
    manage_skills.setObjectName("manage_default_skills_button")
    manage_skills.clicked.connect(lambda: owner.settings_nav.setCurrentRow(6))
    pills_widget = QWidget()
    pills = QHBoxLayout(pills_widget)
    pills.setContentsMargins(0, 0, 0, 0)
    pills.setSpacing(10)
    skills.addWidget(pills_widget)
    def update_pills(text):
        while pills.count():
            item = pills.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        for name in [name.strip() for name in text.split(",") if name.strip()] or ["尚未选择默认技能"]:
            label = QLabel(name)
            label.setProperty("role", "badge")
            pills.addWidget(label)
        pills.addStretch()
        pills_widget.updateGeometry()
    default_skills_edit.textChanged.connect(update_pills)
    update_pills("")
    skills.addWidget(hint("默认技能在新对话中生效，角色也可以使用自己的技能配置。"))
    skills.addWidget(manage_skills, alignment=Qt.AlignmentFlag.AlignLeft)
    page.addStretch()

    return SystemSettingsTabParts(
        widget=widget,
        lang_combo=lang_combo,
        voice_lang_combo=voice_lang_combo,
        default_skills_edit=default_skills_edit,
        always_on_top_check=always_on_top_check,
        reduce_motion_check=reduce_motion_check,
        typewriter_enabled_check=typewriter_enabled_check,
        typewriter_cps_spin=typewriter_cps_spin,
        update_panel=update_panel,
    )
