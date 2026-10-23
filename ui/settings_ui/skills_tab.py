from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget, QInputDialog

from core.skills.repository import SkillRepository
from config.schema import SkillPreset
from ui.settings_ui.presentation import page_layout, FlowLayout, ResponsiveColumns, hint
from ui.settings_ui.list_cards import CardListDelegate


class SkillsTabController:
    def __init__(self, parent: Any, config_manager: Any, repository_factory=None):
        self.parent = parent
        self.config = config_manager
        self._repository_factory = repository_factory or SkillRepository
        self._skill_repository = None
        self._loaded = False
        self.widget = self._build_widget()

    def _build_widget(self) -> QWidget:
        widget = QWidget()
        layout = page_layout(widget, "Skills", "勾选全局默认技能。角色默认 Skills 可在角色管理中单独填写。")

        skill_group = QGroupBox("全局默认 Skills")
        skill_group_layout = QVBoxLayout(skill_group)

        self.system_skill_list = QListWidget()
        self.system_skill_list.setMinimumHeight(180)
        skill_group_layout.addWidget(hint("勾选要在新对话中默认启用的技能。"))
        self.system_skill_list.setProperty("role", "cards")
        self.system_skill_list.setItemDelegate(CardListDelegate(self.system_skill_list, formatter=lambda index: tuple((str(index.data()).replace(" — ", "\n", 1) + "\n").split("\n", 1))))
        self.system_skill_list.setWordWrap(True)
        self.system_skill_list.setMinimumHeight(310)
        skill_group_layout.addWidget(self.system_skill_list)
        self.add_default_skill_button = QPushButton("按名称添加默认 Skill")
        self.add_default_skill_button.setToolTip("手动填写尚未出现在本地列表中的技能名称；勾选后保存配置。")
        self.add_default_skill_button.clicked.connect(self._add_default_skill)
        skill_group_layout.addWidget(self.add_default_skill_button)

        self.skill_preset_list = QListWidget()
        self.skill_preset_list.setMinimumHeight(310)
        self.skill_preset_list.setProperty("role", "cards")
        preset_group = QGroupBox("技能预设")
        preset_layout = QVBoxLayout(preset_group)
        preset_layout.addWidget(hint("管理可重复使用的技能组合。"))
        preset_layout.addWidget(self.skill_preset_list)

        preset_button_layout = FlowLayout()
        self.add_skill_preset_button = QPushButton("新增预设")
        self.rename_skill_preset_button = QPushButton("重命名预设")
        self.delete_skill_preset_button = QPushButton("删除预设")
        self.add_skill_preset_button.clicked.connect(self._add_skill_preset)
        self.rename_skill_preset_button.clicked.connect(self._rename_skill_preset)
        self.delete_skill_preset_button.clicked.connect(self._delete_skill_preset)
        preset_button_layout.addWidget(self.add_skill_preset_button)
        preset_button_layout.addWidget(self.rename_skill_preset_button)
        preset_button_layout.addWidget(self.delete_skill_preset_button)
        preset_button_layout.addStretch()
        preset_layout.addLayout(preset_button_layout)
        self.delete_skill_preset_button.setProperty("role", "danger")
        self.add_skill_preset_button.setProperty("role", "primary")

        layout.addWidget(ResponsiveColumns([skill_group, preset_group], breakpoint=800))
        layout.addStretch()
        return widget

    def refresh(self, *, preserve_selection=False) -> None:
        selected = self.collect_default_skills() if preserve_selection and self._loaded else None
        self.system_skill_list.blockSignals(True)
        self.system_skill_list.clear()
        self.skill_preset_list.clear()

        sys_cfg = self.config.system_config
        default_skills = set(selected if selected is not None else (getattr(sys_cfg, "default_skills", []) or []))
        available = set()
        skills_root = getattr(sys_cfg, "skills_root", "")
        if skills_root:
            self._skill_repository = self._repository_factory([skills_root])
            for skill in self._skill_repository.list_skills():
                available.add(skill.name)
                item = QListWidgetItem(f"{skill.name} — {skill.description}")
                item.setData(Qt.ItemDataRole.UserRole, skill.name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if skill.name in default_skills else Qt.CheckState.Unchecked)
                self.system_skill_list.addItem(item)

        for name in sorted(default_skills - available):
            item = QListWidgetItem(f"{name} — 当前未找到，保留配置")
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.system_skill_list.addItem(item)
        self.system_skill_list.blockSignals(False)
        self._loaded = True
        if hasattr(self.parent, "_sync_default_skills_summary"):
            self.parent._sync_default_skills_summary()

        for preset in getattr(sys_cfg, "skill_presets", []) or []:
            self.skill_preset_list.addItem(getattr(preset, "name", ""))

    def collect_default_skills(self) -> list[str]:
        selected = []
        for row in range(self.system_skill_list.count()):
            item = self.system_skill_list.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                skill_name = item.data(Qt.ItemDataRole.UserRole) or ""
                if skill_name:
                    selected.append(skill_name)
        return selected

    def _add_default_skill(self):
        names, ok = QInputDialog.getText(self.parent, "添加默认 Skills", "技能名称（多个名称用逗号分隔）：")
        if not ok:
            return
        existing = {self.system_skill_list.item(row).data(Qt.ItemDataRole.UserRole): self.system_skill_list.item(row)
                    for row in range(self.system_skill_list.count())}
        for name in dict.fromkeys(item.strip() for item in names.split(",") if item.strip()):
            item = existing.get(name)
            if item is None:
                item = QListWidgetItem(f"{name} — 手动添加")
                item.setData(Qt.ItemDataRole.UserRole, name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                self.system_skill_list.addItem(item)
            item.setCheckState(Qt.CheckState.Checked)

    def _add_skill_preset(self) -> None:
        name, ok = QInputDialog.getText(self.parent, "新增技能预设", "预设名称：")
        if not ok:
            return
        preset_name = name.strip()
        if not preset_name:
            return

        sys_cfg = self.config.system_config
        skill_presets = list(getattr(sys_cfg, "skill_presets", []) or [])
        skill_presets.append(SkillPreset(name=preset_name, skills=[]))
        sys_cfg.skill_presets = skill_presets
        self.refresh(preserve_selection=True)

    def _rename_skill_preset(self) -> None:
        row = self.skill_preset_list.currentRow()
        if row < 0:
            return

        sys_cfg = self.config.system_config
        skill_presets = list(getattr(sys_cfg, "skill_presets", []) or [])
        if row >= len(skill_presets):
            return

        current_name = getattr(skill_presets[row], "name", "")
        name, ok = QInputDialog.getText(self.parent, "重命名技能预设", "预设名称：", text=current_name)
        if not ok:
            return
        preset_name = name.strip()
        if not preset_name:
            return

        skill_presets[row].name = preset_name
        sys_cfg.skill_presets = skill_presets
        self.refresh(preserve_selection=True)
        self.skill_preset_list.setCurrentRow(row)

    def _delete_skill_preset(self) -> None:
        row = self.skill_preset_list.currentRow()
        if row < 0:
            return

        sys_cfg = self.config.system_config
        skill_presets = list(getattr(sys_cfg, "skill_presets", []) or [])
        if row >= len(skill_presets):
            return

        del skill_presets[row]
        sys_cfg.skill_presets = skill_presets
        self.refresh(preserve_selection=True)
        if self.skill_preset_list.count() > 0:
            self.skill_preset_list.setCurrentRow(min(row, self.skill_preset_list.count() - 1))
