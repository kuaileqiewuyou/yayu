"""设置界面窗口"""
import json
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton,
    QMessageBox, QListWidget, QListWidgetItem,
    QFileDialog, QSizeGrip, QSizePolicy, QInputDialog, QTableWidgetItem,
    QLineEdit, QTextEdit, QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox,
)
from PySide6.QtCore import QEvent, Qt, QUrl, QSize, QSignalBlocker, Signal
from PySide6.QtGui import QDesktopServices

from config.config_manager import ConfigManager
from config.llm_providers import llm_provider_choice, provider_setting
from core.runtime.application_identity import APPLICATION_DISPLAY_NAME
from ui import motion
from ui.resources import application_icon, ensure_ui_font, set_button_icon
from ui.settings_ui.page_transition import PageTransition
from core.templates.template_package import TemplatePackageSummary, load_template_import_data, scan_template_packages
from core.security.allowed_roots import AllowedRootsStore
from core.security.bootstrap import get_allowed_roots_store
from ui.settings_ui.api_tab import (
    PROVIDERS as _API_PROVIDERS,
    available_t2i_providers as _available_t2i_providers,
    build_api_tab,
)
from ui.settings_ui.api_controller import APISettingsController
from ui.settings_ui.background_tab import build_background_tab
from ui.settings_ui.tts_tab import build_tts_tab, available_tts_providers as _available_tts_providers
from ui.settings_ui.system_tab import build_system_tab
from ui.settings_ui.web_tab import build_web_tab
from ui.settings_ui.mcp_tab import (
    build_mcp_tab,
    draft_snapshot_for_servers,
    format_mcp_server_detail,
    format_mcp_server_row,
    format_mcp_summary,
)
from ui.settings_ui.mcp_controller import MCPSettingsController
from ui.settings_ui.skills_tab import SkillsTabController
from ui.settings_ui.character_tab import build_character_tab
from ui.settings_ui.character_controller import CharacterSettingsController
from ui.settings_ui.security_tab import build_security_tab, root_row_text
from ui.settings_ui.template_controller import (
    TemplateLibraryWorkflow,
    TemplatePackageWorkflow,
    TemplatePublishDraftWorkflow,
    TemplateReleaseArtifactWorkflow,
    TemplateSaveWorkflow,
    TemplateSettingsController,
)
from ui.settings_ui.save_service import load_settings_into_controls, save_settings_from_controls
from ui.settings_ui.daylight import settings_qss, COLOR_OK, COLOR_WARN, COLOR_ERR, icon
from ui.settings_ui.presentation import decorate_actions
from ui.window_chrome import WindowDragController
from core.skills.repository import SkillRepository





# 兼容旧调用：实际 API/T2I tab 数据与控件构建在 ui.settings_ui.api_tab
PROVIDERS = _API_PROVIDERS

def available_tts_providers() -> list[str]:
    """Return TTS providers selectable in settings."""
    return _available_tts_providers()


def available_t2i_providers() -> list[str]:
    """Return T2I/CG providers selectable in settings."""
    return _available_t2i_providers()


class SettingsWindow(QMainWindow):
    """设置中心主窗口"""

    background_changed = Signal(str)
    always_on_top_changed = Signal(bool)
    character_selected = Signal(str)

    def __init__(self, *, allowed_roots_store: AllowedRootsStore | None = None):
        super().__init__()
        ensure_ui_font()
        self.setWindowIcon(application_icon())
        self.setObjectName("settings_window")
        self.setAccessibleName("Yayu settings window")
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.config = ConfigManager()
        self._active_character_id = str(getattr(self.config.system_config, "active_character_id", "") or "")
        if not self._active_character_id and self.config.characters:
            self._active_character_id = self.config.characters[0].memory_id
        self._character_switch_managed = False
        self._character_switch_enabled = True
        self._loading_settings = True
        self._llm_provider_drafts = {}
        self._active_llm_provider = None
        self._settings_dirty = False
        self.allowed_roots_store = allowed_roots_store or get_allowed_roots_store()
        self._mcp_runtime_controller = None
        self._mcp_form_syncing = False
        self._mcp_selected_row = -1
        self._current_character_index = 0
        self.skills_tab = None
        self.character_controller = CharacterSettingsController(self)
        self.template_library_workflow = TemplateLibraryWorkflow(
            lambda: self._template_library_root(),
            scan_template_packages,
            ensure_directory=lambda path: path.mkdir(parents=True, exist_ok=True),
            open_directory=lambda path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))),
        )
        self.template_package_workflow = TemplatePackageWorkflow()
        self.template_publish_draft_workflow = TemplatePublishDraftWorkflow()
        self.template_release_artifact_workflow = TemplateReleaseArtifactWorkflow()
        self.template_save_workflow = TemplateSaveWorkflow()
        self.character_card_buttons = []
        self.character_card_avatar_labels = []
        self.character_card_use_buttons = []

        self.setMinimumSize(800, 600)
        self._apply_default_size()
        self.setWindowTitle(f"{APPLICATION_DISPLAY_NAME} · 设置中心")
        self.setStyleSheet(settings_qss())
        self._init_ui()
        self._load_config()
        self._loading_settings = False
        self._connect_dirty_tracking()
        decorate_actions(self)
        self._set_status_message("● 配置已加载")

    def _mark_settings_dirty(self, *_):
        if not self._loading_settings:
            self._settings_dirty = True
            if self.settings_tabs.currentIndex() not in (8, 9):
                self._set_status_message("● 有未保存的更改")

    def _connect_dirty_tracking(self):
        # Navigation, template filters and the independent memory editor are excluded.
        for root in (self._api_tab_parts.widget, self._tts_tab_parts.widget,
                     self._system_tab_parts.widget, self._web_tab_parts.widget,
                     self._background_tab_parts.widget):
            for control in root.findChildren(QWidget):
                self._connect_editor_change(control)
        for control in (self.char_name_edit, self.char_default_skills_edit, self.char_setting_edit,
                        self.refer_audio_path_edit, self.prompt_text_edit, self.prompt_lang_combo,
                        self.speech_speed_spin, self.avatar_path_edit, self.emotion_tags_edit):
            self._connect_editor_change(control)
        self.emotion_binding_table.itemChanged.connect(self._mark_settings_dirty)
        self.system_skill_list.itemChanged.connect(self._mark_settings_dirty)
        for items in (self.scene_list, self.sprite_list, self.skill_preset_list):
            items.model().rowsInserted.connect(self._mark_settings_dirty)
            items.model().rowsRemoved.connect(self._mark_settings_dirty)
        self.scene_list.bindingsChanged.connect(self._mark_settings_dirty)

    def _connect_editor_change(self, control):
        if control.property("settingsIndependent"):
            return
        if isinstance(control, QLineEdit):
            control.textEdited.connect(self._mark_settings_dirty)
        elif isinstance(control, QTextEdit):
            control.textChanged.connect(self._mark_settings_dirty)
        elif isinstance(control, QComboBox):
            control.activated.connect(self._mark_settings_dirty)
        elif isinstance(control, QCheckBox):
            control.toggled.connect(self._mark_settings_dirty)
        elif isinstance(control, (QSpinBox, QDoubleSpinBox)):
            control.valueChanged.connect(self._mark_settings_dirty)

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 标题栏（settings-titlebar，「芽语 · 设置中心」）──
        titlebar = QWidget()
        titlebar.setObjectName("settings_titlebar")
        self.settings_titlebar = titlebar
        titlebar_layout = QHBoxLayout(titlebar)
        titlebar_layout.setContentsMargins(18, 8, 12, 8)
        titlebar_layout.setSpacing(10)
        self.settings_app_icon = QLabel()
        self.settings_app_icon.setObjectName("settings_app_icon")
        self.settings_app_icon.setPixmap(self.windowIcon().pixmap(24, 24))
        titlebar_layout.addWidget(self.settings_app_icon)
        title_label = QLabel(f"{APPLICATION_DISPLAY_NAME} · 设置中心")
        title_label.setObjectName("settings_title_label")
        titlebar_layout.addWidget(title_label)
        titlebar_layout.addStretch()
        self.settings_minimize_button = self._make_titlebar_button(
            "—", "settings_minimize_button", "Minimize settings", "最小化设置中心", self.showMinimized
        )
        self.settings_maximize_button = self._make_titlebar_button(
            "□", "settings_maximize_button", "Maximize settings", "最大化设置中心", self._toggle_maximized
        )
        self.settings_close_button = self._make_titlebar_button(
            "×", "settings_close_button", "Close settings", "关闭设置中心", self.close, close=True
        )
        titlebar_layout.addWidget(self.settings_minimize_button)
        titlebar_layout.addWidget(self.settings_maximize_button)
        titlebar_layout.addWidget(self.settings_close_button)
        layout.addWidget(titlebar)
        self._window_drag_controller = WindowDragController(
            self, [titlebar, title_label], toggle_maximize=True
        )

        # ── 主体：左侧导航 + 右侧内容页（mockup: settings-body）──
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # 内容页仍由 QTabWidget 承载（隐藏标签栏，导航由左侧列表驱动，
        # 保留 settings_tabs 语义锚点与既有 add/currentIndex 接口）
        tabs = QTabWidget()
        tabs.setObjectName("settings_tabs")
        tabs.setAccessibleName("Settings tabs")
        tabs.tabBar().setVisible(False)
        tabs.setStyleSheet("QTabWidget::pane { border: none; border-radius: 0; background: transparent; }")
        self.settings_tabs = tabs
        tabs.addTab(self._create_api_tab(), "模型配置")
        self.character_tab = build_character_tab(self)
        self.character_stack = self.character_tab.character_stack
        self.character_overview_page = self.character_tab.character_overview_page
        self.character_detail_page = self.character_tab.character_detail_page
        self.return_character_list_button = self.character_tab.return_character_list_button
        self.character_overview_title_label = self.character_tab.character_overview_title_label
        self.character_overview_summary_label = self.character_tab.character_overview_summary_label
        self.character_list = self.character_tab.character_list
        self.character_card_grid = self.character_tab.character_card_grid
        self.character_card_grid_layout = self.character_tab.character_card_grid_layout
        self.character_card_grid.width_changed.connect(self.character_controller.reflow_character_cards)
        self.character_empty_state_label = self.character_tab.character_empty_state_label
        self.character_detail_content_widget = self.character_tab.character_detail_content_widget
        self.add_character_button = self.character_tab.add_character_button
        self.sprite_list = self.character_tab.sprite_list
        self.import_sprites_button = self.character_tab.import_sprites_button
        self.preview_sprite_button = self.character_tab.preview_sprite_button
        self.delete_sprite_button = self.character_tab.delete_sprite_button
        self.char_name_edit = self.character_tab.char_name_edit
        self.char_default_skills_edit = self.character_tab.char_default_skills_edit
        self.char_setting_edit = self.character_tab.char_setting_edit
        self.voice_group = self.character_tab.voice_group
        self.refer_audio_path_edit = self.character_tab.refer_audio_path_edit
        self.browse_refer_audio_button = self.character_tab.browse_refer_audio_button
        self.prompt_text_edit = self.character_tab.prompt_text_edit
        self.prompt_lang_combo = self.character_tab.prompt_lang_combo
        self.speech_speed_spin = self.character_tab.speech_speed_spin
        self.clear_voice_button = self.character_tab.clear_voice_button
        self.avatar_preview_label = self.character_tab.avatar_preview_label
        self.avatar_status_label = self.character_tab.avatar_status_label
        self.avatar_path_edit = self.character_tab.avatar_path_edit
        self.import_avatar_button = self.character_tab.import_avatar_button
        self.clear_avatar_button = self.character_tab.clear_avatar_button
        self.emotion_tags_edit = self.character_tab.emotion_tags_edit
        self.emotion_tags_label = self.character_tab.emotion_tags_label
        self.emotion_binding_table = self.character_tab.emotion_binding_table
        self.add_emotion_binding_button = self.character_tab.add_emotion_binding_button
        self.fill_default_emotions_button = self.character_tab.fill_default_emotions_button
        self.delete_emotion_binding_button = self.character_tab.delete_emotion_binding_button
        self.template_sample_output_edit = self.character_tab.template_sample_output_edit
        self.template_sample_type_combo = self.character_tab.template_sample_type_combo
        self.template_validate_button = self.character_tab.template_validate_button
        self.template_fill_sample_button = self.character_tab.template_fill_sample_button

        self.template_preflight_button = self.character_tab.template_preflight_button
        self.template_publish_handoff_button = self.character_tab.template_publish_handoff_button
        self.template_export_draft_button = self.character_tab.template_export_draft_button
        self.template_export_package_button = self.character_tab.template_export_package_button
        self.template_save_to_library_button = self.character_tab.template_save_to_library_button
        self.template_copy_validation_result_button = self.character_tab.template_copy_validation_result_button
        self.template_validation_result_label = self.character_tab.template_validation_result_label
        self.template_refresh_library_button = self.character_tab.template_refresh_library_button
        self.template_import_selected_button = self.character_tab.template_import_selected_button
        self.template_open_library_button = self.character_tab.template_open_library_button
        self.template_library_search_edit = self.character_tab.template_library_search_edit
        self.template_library_filter_combo = self.character_tab.template_library_filter_combo
        self.template_library_result_summary_label = self.character_tab.template_library_result_summary_label
        self.template_library_sort_combo = self.character_tab.template_library_sort_combo
        self.template_library_preflight_filter_combo = self.character_tab.template_library_preflight_filter_combo
        self.template_library_time_filter_combo = self.character_tab.template_library_time_filter_combo
        self.template_library_clear_filters_button = self.character_tab.template_library_clear_filters_button
        self.template_library_list = self.character_tab.template_library_list
        self.template_library_detail_label = self.character_tab.template_library_detail_label
        tabs.addTab(self.character_tab.widget, "角色管理")
        self.character_list.currentRowChanged.connect(self._on_character_selection_changed)
        self.add_character_button.clicked.connect(self._add_character)
        self.return_character_list_button.clicked.connect(self._show_character_overview_page)
        self.import_avatar_button.clicked.connect(self._import_avatar_for_current_character)
        self.clear_avatar_button.clicked.connect(self._clear_avatar_for_current_character)
        self.import_sprites_button.clicked.connect(self._import_sprites_for_current_character)
        self.preview_sprite_button.clicked.connect(self._preview_selected_sprite)
        self.delete_sprite_button.clicked.connect(self._delete_selected_sprite)
        self.sprite_list.itemDoubleClicked.connect(lambda _item: self._preview_selected_sprite())
        self.sprite_list.itemSelectionChanged.connect(self._update_sprite_actions)
        self.browse_refer_audio_button.clicked.connect(self._browse_refer_audio)
        self.clear_voice_button.clicked.connect(self._clear_gpt_sovits_voice)
        self.add_emotion_binding_button.clicked.connect(self._add_emotion_binding_row)
        self.fill_default_emotions_button.clicked.connect(self._fill_default_emotion_bindings)
        self.delete_emotion_binding_button.clicked.connect(self._delete_selected_emotion_binding_row)
        self._update_character_detail_visibility(False)

        tabs.addTab(self._create_background_tab(), "背景设置")
        tabs.addTab(self._create_tts_tab(), "语音设定")
        tabs.addTab(self._create_system_tab(), "系统设定")

        tabs.addTab(self._create_web_tab(), "联网搜索")
        self.skills_tab = SkillsTabController(self, self.config, repository_factory=lambda roots: SkillRepository(roots))
        self.system_skill_list = self.skills_tab.system_skill_list
        self.skill_preset_list = self.skills_tab.skill_preset_list
        self.add_skill_preset_button = self.skills_tab.add_skill_preset_button
        self.rename_skill_preset_button = self.skills_tab.rename_skill_preset_button
        self.delete_skill_preset_button = self.skills_tab.delete_skill_preset_button
        tabs.addTab(self.skills_tab.widget, "Skills")

        self._mcp_tab_parts = build_mcp_tab(self)

        self.mcp_redetect_button = self._mcp_tab_parts.redetect_button
        self.mcp_add_server_button = self._mcp_tab_parts.add_server_button
        self.mcp_remove_server_button = self._mcp_tab_parts.remove_server_button
        self.mcp_test_server_button = self._mcp_tab_parts.test_server_button
        self.mcp_summary_label = self._mcp_tab_parts.summary_label
        self.mcp_server_list = self._mcp_tab_parts.server_list
        self.mcp_detail_label = self._mcp_tab_parts.detail_label
        self.mcp_name_edit = self._mcp_tab_parts.name_edit
        self.mcp_transport_combo = self._mcp_tab_parts.transport_combo
        self.mcp_enabled_check = self._mcp_tab_parts.enabled_check
        self.mcp_http_url_edit = self._mcp_tab_parts.http_url_edit
        self.mcp_json_edit = self._mcp_tab_parts.json_edit
        self.mcp_save_server_button = self._mcp_tab_parts.save_server_button
        tabs.addTab(self._mcp_tab_parts.widget, "工具 / MCP")

        self._security_tab_parts = build_security_tab(self, self.allowed_roots_store)
        self.security_allowed_roots_list = self._security_tab_parts.allowed_roots_list
        self.security_add_root_button = self._security_tab_parts.add_root_button
        self.security_remove_root_button = self._security_tab_parts.remove_root_button
        self.security_status_label = self._security_tab_parts.status_label
        self.security_add_root_button.clicked.connect(self._add_allowed_root)
        self.security_remove_root_button.clicked.connect(self._remove_selected_allowed_root)
        self.security_allowed_roots_list.currentRowChanged.connect(self._update_security_remove_button)
        tabs.addTab(self._security_tab_parts.widget, "权限与安全")
        self._refresh_allowed_roots()

        from ui.settings_ui.memory_tab import MemoryTab
        self.memory_tab = MemoryTab(self.config, self)
        tabs.addTab(self.memory_tab, "记忆管理")

        # 左侧导航（mockup: settings-nav）
        self.settings_nav = QListWidget()
        self.settings_nav.setObjectName("settings_nav")
        self.settings_nav.setAccessibleName("Settings navigation")
        self.settings_nav.setFixedWidth(178)
        self.settings_nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_icons = ["model", "character", "image", "voice", "system", "search", "skills", "tools", "security", "memory"]
        self.settings_nav.setIconSize(QSize(22, 22))
        for index in range(tabs.count()):
            self.settings_nav.addItem(QListWidgetItem(icon(nav_icons[index]), "  " + tabs.tabText(index)))
        self.settings_nav.setCurrentRow(tabs.currentIndex())
        self.settings_nav.currentRowChanged.connect(tabs.setCurrentIndex)

        body_layout.addWidget(self.settings_nav)
        content_column = QWidget()
        content_layout = QVBoxLayout(content_column)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(tabs, 1)
        body_layout.addWidget(content_column, stretch=1)
        layout.addWidget(body, stretch=1)

        # 底部状态提示与按钮
        bottom_bar = QWidget()
        bottom_bar.setObjectName("settings_bottom_bar")
        btn_layout = QHBoxLayout(bottom_bar)
        btn_layout.setContentsMargins(18, 10, 18, 10)
        self.save_status_label = QLabel("修改后请保存配置")
        self.save_status_label.setObjectName("save_status_label")
        self.save_status_label.setAccessibleName("Save status")
        self.save_status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.save_status_label.setMinimumWidth(0)
        self.save_status_label.setMaximumHeight(24)
        self.save_status_label.setWordWrap(False)
        self.save_status_label.setProperty("role", "muted")
        self.save_settings_button = QPushButton("保存配置")
        self.save_settings_button.setObjectName("save_settings_button")
        self.save_settings_button.setAccessibleName("Save settings")
        self.save_settings_button.setProperty("role", "primary")
        self.save_settings_button.setMinimumWidth(140)
        self.save_settings_button.clicked.connect(self._save_config)
        btn_layout.addWidget(self.save_status_label, 1)
        btn_layout.addWidget(self.save_settings_button)
        self.settings_size_grip = QSizeGrip(self)
        self.settings_size_grip.setObjectName("settings_size_grip")
        self.settings_size_grip.setAccessibleName("Resize settings window")
        self.settings_size_grip.setToolTip("拖动调整窗口大小")
        self.settings_size_grip.setFixedSize(18, 18)
        btn_layout.addWidget(self.settings_size_grip)
        content_layout.addWidget(bottom_bar)
        self._last_settings_page = tabs.currentIndex()
        self._page_transition = PageTransition(tabs)
        tabs.currentChanged.connect(self._on_settings_page_changed)
        self.system_skill_list.itemChanged.connect(self._sync_default_skills_summary)

    def _sync_default_skills_summary(self, *_):
        self.system_default_skills_edit.setText(", ".join(self.skills_tab.collect_default_skills()))

    def _on_settings_page_changed(self, index):
        previous = self._last_settings_page
        if previous == 9 and index != 9 and not self.memory_tab.confirm_pending_edits():
            self._page_transition.finish()
            with QSignalBlocker(self.settings_tabs):
                self.settings_tabs.setCurrentIndex(previous)
            with QSignalBlocker(self.settings_nav):
                self.settings_nav.setCurrentRow(previous)
            return
        self._last_settings_page = index
        with QSignalBlocker(self.settings_nav):
            self.settings_nav.setCurrentRow(index)
        self.save_settings_button.setVisible(index not in (8, 9))
        if index == 8:
            text = "目录授权即时保存；重启应用后生效"
        elif index == 9:
            text = "记忆范围与单条记忆分别保存"
        else:
            text = "● 有未保存的更改" if self._settings_dirty else "● 配置已加载"
        self._set_status_message(text)
        if previous != index:
            self._page_transition.start(
                self.settings_tabs.currentWidget(),
                direction=1 if index > previous else -1,
                enabled=not self.reduce_motion_check.isChecked(),
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "settings_nav"):
            compact = self.width() < 1000
            self.settings_nav.setFixedWidth(154 if compact else 240)
            if hasattr(self, "character_tab"):
                self.character_tab.header_avatar.setVisible(not compact)
                self.character_tab.header_name.setVisible(not compact)
            if self.property("compact") != compact:
                self.setProperty("compact", compact)
                self.setStyleSheet(settings_qss())

    def _refresh_allowed_roots(self) -> None:
        roots = self.allowed_roots_store.load()
        self.security_allowed_roots_list.clear()
        for root in roots:
            self.security_allowed_roots_list.addItem(
                root_row_text(root, project_root=self.allowed_roots_store.project_root)
            )
        if roots:
            self.security_allowed_roots_list.setCurrentRow(0)
        self._update_security_remove_button(self.security_allowed_roots_list.currentRow())

    def _update_security_remove_button(self, row: int) -> None:
        roots = self.allowed_roots_store.load()
        removable = 0 <= row < len(roots) and roots[row] != self.allowed_roots_store.project_root
        self.security_remove_root_button.setEnabled(removable)

    def _add_allowed_root(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择要授权的目录")
        if not selected:
            return
        try:
            self.allowed_roots_store.add(selected)
        except (OSError, ValueError) as exc:
            self.security_status_label.setText(f"添加授权失败：{exc}")
            return
        self._refresh_allowed_roots()
        self.security_status_label.setText("目录授权已保存；重启应用后对 Agent 工具生效。")

    def _remove_selected_allowed_root(self) -> None:
        roots = self.allowed_roots_store.load()
        row = self.security_allowed_roots_list.currentRow()
        if row < 0 or row >= len(roots):
            return
        try:
            self.allowed_roots_store.remove(roots[row])
        except (OSError, PermissionError) as exc:
            self.security_status_label.setText(f"移除授权失败：{exc}")
            return
        self._refresh_allowed_roots()
        self.security_status_label.setText("目录授权已移除；重启应用后对 Agent 工具生效。")

    def _apply_default_size(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(1100, 760)
            return
        available = screen.availableGeometry().size()
        width = max(self.minimumWidth(), min(1100, int(available.width() * 0.9)))
        height = max(self.minimumHeight(), min(760, int(available.height() * 0.9)))
        self.resize(width, height)

    def _make_titlebar_button(self, text, object_name, accessible_name, tooltip, callback, *, close=False):
        button = QPushButton(text)
        set_button_icon(button, {"—": "minus", "□": "maximize", "×": "close"}[text], 16)
        button.setObjectName(object_name)
        button.setAccessibleName(accessible_name)
        button.setToolTip(tooltip)
        button.setFixedSize(32, 32)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("role", "chrome")
        button.clicked.connect(callback)
        return button

    def _toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self._update_maximize_button()

    def _update_maximize_button(self) -> None:
        maximized = self.isMaximized()
        set_button_icon(self.settings_maximize_button, "restore" if maximized else "maximize", 16)
        self.settings_maximize_button.setAccessibleName(
            "Restore settings" if maximized else "Maximize settings"
        )
        self.settings_maximize_button.setToolTip(
            "还原设置中心" if maximized else "最大化设置中心"
        )
        self.settings_size_grip.setVisible(not maximized)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "settings_maximize_button"):
            self._update_maximize_button()

    def _create_api_tab(self) -> QWidget:
        self._api_tab_parts = build_api_tab(self)
        self.llm_provider_combo = self._api_tab_parts.llm_provider_combo
        self.api_key_edit = self._api_tab_parts.api_key_edit
        self.base_url_edit = self._api_tab_parts.base_url_edit
        self.model_edit = self._api_tab_parts.model_edit
        self.llm_check_button = self._api_tab_parts.llm_check_button
        self.temp_spin = self._api_tab_parts.temp_spin
        self.stream_check = self._api_tab_parts.stream_check
        self.t2i_provider_combo = self._api_tab_parts.t2i_provider_combo
        self.t2i_api_url_edit = self._api_tab_parts.t2i_api_url_edit
        self.t2i_checkpoint_edit = self._api_tab_parts.t2i_checkpoint_edit
        self.t2i_check_button = self._api_tab_parts.t2i_check_button
        self.t2i_hint_label = self._api_tab_parts.t2i_hint_label
        return self._api_tab_parts.widget

    def _create_web_tab(self) -> QWidget:
        self._web_tab_parts = build_web_tab(self)
        self.web_search_enabled_check = self._web_tab_parts.enabled_check
        self.web_search_region_combo = self._web_tab_parts.region_combo
        self.web_search_safesearch_combo = self._web_tab_parts.safesearch_combo
        self.web_search_max_results_spin = self._web_tab_parts.max_results_spin
        self.web_extract_timeout_spin = self._web_tab_parts.timeout_spin
        self.web_extract_max_chars_spin = self._web_tab_parts.max_chars_spin
        self.web_search_hint_label = self._web_tab_parts.hint_label
        return self._web_tab_parts.widget

    def _create_background_tab(self) -> QWidget:
        self._background_tab_parts = build_background_tab(self)
        self.scene_list = self._background_tab_parts.scene_list
        self.add_scene_button = self._background_tab_parts.add_scene_button
        self.remove_scene_button = self._background_tab_parts.remove_scene_button
        self.background_path_combo = self._background_tab_parts.background_path_combo
        return self._background_tab_parts.widget

    def set_current_background(self, path: str) -> None:
        """Synchronize a choice made in chat without creating a settings draft."""
        self.background_path_combo.set_current_background(path)

    def show_background_settings(self) -> None:
        self.settings_nav.setCurrentRow(2)
        self.show()
        self.raise_()
        self.activateWindow()

    def _add_scene(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择场景图片", "", "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)")
        for f in files:
            self.scene_list.addItem(f)

    def _remove_selected(self, list_widget: QListWidget):
        for item in list_widget.selectedItems():
            list_widget.takeItem(list_widget.row(item))

    def _create_tts_tab(self) -> QWidget:
        self._tts_tab_parts = build_tts_tab(self)
        self.tts_provider_combo = self._tts_tab_parts.provider_combo
        self.tts_url_edit = self._tts_tab_parts.url_edit
        self.tts_voice_edit = self._tts_tab_parts.voice_edit
        self.tts_speed_spin = self._tts_tab_parts.speed_spin
        self.tts_hint_label = self._tts_tab_parts.hint_label
        return self._tts_tab_parts.widget

    def _create_system_tab(self) -> QWidget:
        self._system_tab_parts = build_system_tab(self)
        self.lang_combo = self._system_tab_parts.lang_combo
        self.voice_lang_combo = self._system_tab_parts.voice_lang_combo
        self.system_default_skills_edit = self._system_tab_parts.default_skills_edit
        self.always_on_top_check = self._system_tab_parts.always_on_top_check
        self.reduce_motion_check = self._system_tab_parts.reduce_motion_check
        self.typewriter_enabled_check = self._system_tab_parts.typewriter_enabled_check
        self.typewriter_cps_spin = self._system_tab_parts.typewriter_cps_spin
        from ui.settings_ui.update_controller import UpdateController
        self.update_controller = UpdateController(self, self._system_tab_parts.update_panel)
        return self._system_tab_parts.widget

    def _on_provider_changed(self, provider: str):
        """Keep each provider's in-progress credentials and endpoint separate."""
        provider = llm_provider_choice(provider)
        if self._loading_settings:
            return
        previous = self._active_llm_provider
        if previous is not None:
            self._llm_provider_drafts[previous] = (
                self.api_key_edit.text(), self.base_url_edit.text(), self.model_edit.text()
            )
        draft = self._llm_provider_drafts.get(provider)
        if draft is None:
            cfg = self.config.api_config
            is_saved_provider = llm_provider_choice(cfg.llm_provider) == provider
            saved_key = cfg.llm_provider if is_saved_provider else provider
            draft = (
                provider_setting(cfg.llm_api_key, saved_key),
                cfg.llm_base_url if is_saved_provider else PROVIDERS[provider]["base_url"],
                provider_setting(cfg.llm_model, saved_key),
            )
        api_key, base_url, model = draft
        self.api_key_edit.setText(api_key)
        self.base_url_edit.setText(base_url)
        self.model_edit.setText(model)
        self._active_llm_provider = provider

    def _reset_llm_provider_drafts(self):
        """A reload replaces previous drafts with the newly loaded form values."""
        self._llm_provider_drafts.clear()
        self._active_llm_provider = self.llm_provider_combo.currentData()

    def _update_tts_provider_hint(self, provider: str):
        if provider == "none":
            text = "TTS 已关闭：角色回复只显示文字，不会合成语音。"
        elif provider == "gpt-sovits":
            text = "gpt-sovits 需要填写 TTS 服务 URL；保存后请重启聊天窗口后生效。"
        else:
            text = f"{provider} 通常不需要填写服务 URL；保存后请重启聊天窗口后生效。"
        self.tts_hint_label.setText(text)
        self.tts_hint_label.setToolTip(text)
        self.tts_url_edit.setEnabled(provider not in ("none", "edge-tts"))
        self.tts_voice_edit.setEnabled(provider == "edge-tts")
        self.tts_speed_spin.setEnabled(provider != "none")

    def _update_t2i_provider_hint(self, provider: str):
        if provider == "none":
            text = "T2I/CG 已关闭：CG token 只会显示系统提示，不会提交图像生成请求。"
        elif provider == "comfyui":
            text = "ComfyUI 需要填写 API URL；Checkpoint 必须填写 ComfyUI 实际已安装模型名称；如果 /prompt 报 ckpt_name not in [...]，请改成已安装模型名称，保存后重启聊天窗口后生效。"
        else:
            text = f"{provider} 需要可访问的图像生成服务；保存后请重启聊天窗口后生效。"
        self.t2i_hint_label.setText(text)
        self.t2i_hint_label.setToolTip(text)
        self.t2i_api_url_edit.setEnabled(provider != "none")
        self.t2i_checkpoint_edit.setEnabled(provider != "none")

    def _set_status_message(self, message: str, *, error: bool = False):
        color = COLOR_ERR if error else COLOR_OK
        self.save_status_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        self.save_status_label.setText(message)
        self.save_status_label.setToolTip(message)

    def set_mcp_runtime_controller(self, controller) -> None:
        self._mcp_runtime_controller = controller

    def refresh_mcp_status(self, snapshot, *, sync_controller_snapshot: bool = True) -> None:
        previous_row = self._mcp_selected_row
        self._mcp_tab_parts.summary_label.setText(format_mcp_summary(snapshot))
        self._mcp_tab_parts.server_list.clear()
        self._mcp_current_snapshot = snapshot
        if snapshot.servers:
            for server in snapshot.servers:
                self._mcp_tab_parts.server_list.addItem(format_mcp_server_row(server))
            self._mcp_tab_parts.empty_state_label.setText("")
            target_row = previous_row if 0 <= previous_row < len(snapshot.servers) else 0
            self._mcp_tab_parts.server_list.setCurrentRow(target_row)
            self._show_selected_mcp_server_detail(target_row)
        else:
            self._mcp_selected_row = -1
            self._mcp_tab_parts.empty_state_label.setText("当前没有可展示的 MCP Server。")
            self._mcp_tab_parts.detail_label.setText("当前没有可展示的 MCP Server。")
            self._populate_mcp_form(None)

    def _show_selected_mcp_server_detail(self, row: int) -> None:
        self._mcp_selected_row = row
        self._mcp_tab_parts.tools_table.setRowCount(0)
        self._mcp_tab_parts.result_label.setText("选择服务器后可测试连接与查看工具。")
        self._mcp_tab_parts.result_label.setProperty("state", "idle")
        self._mcp_tab_parts.result_label.style().unpolish(self._mcp_tab_parts.result_label)
        self._mcp_tab_parts.result_label.style().polish(self._mcp_tab_parts.result_label)
        if row < 0:
            self._mcp_tab_parts.detail_label.setText("未选择 MCP Server。")
            self._populate_mcp_form(None)
            return
        snapshot = None
        if self._mcp_runtime_controller is not None:
            snapshot = self._mcp_runtime_controller.last_snapshot
        elif hasattr(self, "_mcp_current_snapshot"):
            snapshot = self._mcp_current_snapshot
        if snapshot is None or row >= len(snapshot.servers):
            self._mcp_tab_parts.detail_label.setText("未找到 MCP Server 详情。")
            self._populate_mcp_form(None)
            return
        self._mcp_tab_parts.detail_label.setText(format_mcp_server_detail(snapshot.servers[row]))
        server = snapshot.servers[row]
        result = self._mcp_tab_parts.result_label
        state_names = {"ready": "连接成功", "failed": "连接失败", "error": "连接失败", "disabled": "已停用", "pending": "等待检测", "unknown": "尚未检测"}
        result.setText(f"{state_names.get(server.state, server.state)} · {server.tool_count} 个工具" + (f"\n{server.error}" if server.error else ""))
        result.setProperty("state", "failed" if server.error else "idle")
        result.style().unpolish(result)
        result.style().polish(result)
        table = self._mcp_tab_parts.tools_table
        table.setRowCount(len(server.discovered_tools))
        for index, name in enumerate(server.discovered_tools):
            table.setItem(index, 0, QTableWidgetItem(name))
            table.setItem(index, 1, QTableWidgetItem(server.discovered_tool_descriptions.get(name, "")))
        table.resizeRowsToContents()
        if row < len(self.config.mcp_servers):
            self._populate_mcp_form(self.config.mcp_servers[row])

    @staticmethod
    def _mcp_server_to_editor_payload(server) -> dict:
        return MCPSettingsController.server_to_editor_payload(server)

    @staticmethod
    def _default_mcp_editor_payload() -> dict:
        return MCPSettingsController.default_editor_payload()

    def _populate_mcp_form(self, server) -> None:
        self._mcp_form_syncing = True
        try:
            if server is None:
                self.mcp_name_edit.clear()
                self.mcp_transport_combo.setCurrentText("stdio")
                self.mcp_enabled_check.setChecked(True)
                self.mcp_http_url_edit.clear()
                payload = self._default_mcp_editor_payload()
            else:
                self.mcp_name_edit.setText(server.name)
                self.mcp_transport_combo.setCurrentText(server.transport)
                self.mcp_enabled_check.setChecked(server.enabled)
                self.mcp_http_url_edit.setText(server.url if server.transport == "http" else "")
                payload = self._mcp_server_to_editor_payload(server)
            self.mcp_json_edit.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))
        finally:
            self._mcp_form_syncing = False

    def _update_selected_mcp_server_from_form(self) -> bool:
        if self._mcp_form_syncing:
            return False
        row = self._mcp_selected_row
        if row < 0 or row >= len(self.config.mcp_servers):
            return False

        updated_server, error_message = MCPSettingsController.server_from_editor_payload(
            row=row,
            current_server=self.config.mcp_servers[row],
            raw_name=self.mcp_name_edit.text(),
            raw_json=self.mcp_json_edit.toPlainText(),
            selected_transport=self.mcp_transport_combo.currentText(),
            selected_enabled=self.mcp_enabled_check.isChecked(),
            selected_http_url=self.mcp_http_url_edit.text(),
        )
        if error_message:
            self._set_status_message(error_message, error=True)
            return False

        servers = list(self.config.mcp_servers)
        servers[row] = updated_server
        self.config.set_mcp_servers(servers)
        self._mcp_selected_row = row
        self.refresh_mcp_status(draft_snapshot_for_servers(servers), sync_controller_snapshot=False)
        self.mcp_server_list.setCurrentRow(row)
        self._set_status_message(f"已更新 MCP Server 草稿：{updated_server.name}。请点击“保存配置”持久化更改。")
        return True

    def _redetect_mcp(self) -> None:
        if self._mcp_runtime_controller is None:
            self._set_status_message("MCP 控制器尚未初始化。", error=True)
            return
        if self.config.mcp_servers and not self._update_selected_mcp_server_from_form():
            return

        result = MCPSettingsController.redetect(
            self._mcp_runtime_controller,
            self.config.mcp_servers,
        )
        self.refresh_mcp_status(result.snapshot, sync_controller_snapshot=False)
        self._set_status_message(result.message, error=result.is_error)

    def _add_mcp_server(self) -> None:
        servers, selected_row, status_message = MCPSettingsController.add_server_draft(self.config.mcp_servers)
        self.config.set_mcp_servers(servers)
        self.refresh_mcp_status(draft_snapshot_for_servers(servers), sync_controller_snapshot=False)
        self._mcp_selected_row = selected_row
        self.mcp_server_list.setCurrentRow(selected_row)
        self._set_status_message(status_message)

    def _remove_selected_mcp_server(self) -> None:
        servers, selected_row, status_message, error_message = MCPSettingsController.remove_selected_server(
            self.config.mcp_servers,
            selected_row=self._mcp_selected_row,
            current_row=self.mcp_server_list.currentRow(),
        )
        if error_message:
            self._set_status_message(error_message, error=True)
            return
        self.config.set_mcp_servers(servers)
        self._mcp_selected_row = selected_row
        self.refresh_mcp_status(draft_snapshot_for_servers(servers), sync_controller_snapshot=False)
        self._set_status_message(status_message or "")

    def _test_selected_mcp_server(self) -> None:
        if self._mcp_runtime_controller is None:
            self._set_status_message("MCP 控制器尚未初始化。", error=True)
            return
        row = self._mcp_selected_row if self._mcp_selected_row >= 0 else self.mcp_server_list.currentRow()
        servers = list(self.config.mcp_servers)
        if row < 0 or row >= len(servers):
            self._set_status_message("请先选择要测试的 MCP Server。", error=True)
            return
        if not self._update_selected_mcp_server_from_form():
            return
        servers = list(self.config.mcp_servers)
        result = MCPSettingsController.test_selected(
            self._mcp_runtime_controller,
            servers,
            row,
        )
        self.refresh_mcp_status(result.snapshot, sync_controller_snapshot=False)
        self.mcp_server_list.setCurrentRow(row)
        self._set_status_message(result.message, error=result.is_error)

    def _set_template_validation_result(self, message: str, *, level: str = "ok"):
        colors = {
            "ok": COLOR_OK,
            "warning": COLOR_WARN,
            "error": COLOR_ERR,
        }
        color = colors.get(level, colors["ok"])
        self.template_validation_result_label.setStyleSheet(f"color: {color};")
        self.template_validation_result_label.setText(message)
        self.template_validation_result_label.setToolTip(message)

    def _set_clipboard_text(self, text: str):
        QApplication.clipboard().setText(text)

    def _copy_template_validation_result(self):
        message = self.template_validation_result_label.text()
        if not message.strip():
            self._set_template_validation_result("暂无可复制的校验结果。", level="error")
            return

        self._set_clipboard_text(message)
        self.template_validation_result_label.setToolTip(message)

    def _validate_template_sample_output(self):
        level, message = TemplateSettingsController.template_validation_result_message(
            self.template_sample_output_edit.toPlainText()
        )
        self._set_template_validation_result(message, level=level)

    def _template_preflight_fix_suggestions(self, errors: list[str], warnings: list[str]) -> list[str]:
        return TemplateSettingsController.template_preflight_fix_suggestions(errors, warnings)

    def _build_template_preflight_report(self, *, require_sample_output: bool = True) -> tuple[str, str]:
        return TemplateSettingsController.build_template_preflight_report(
            character_name=self.char_name_edit.text(),
            character_setting=self.char_setting_edit.toPlainText(),
            emotion_tags=self.emotion_tags_edit.toPlainText(),
            sample_output=self.template_sample_output_edit.toPlainText(),
            require_sample_output=require_sample_output,
        )

    def _run_template_preflight_check(self):
        level, message = self._build_template_preflight_report()
        self._set_template_validation_result(message, level=level)

    def _template_sample_token_coverage(self, sample_output: str) -> str:
        return TemplateSettingsController.template_sample_token_coverage(sample_output)

    def _build_template_publish_handoff_report(self) -> tuple[str, str]:
        return TemplateSettingsController.build_template_publish_handoff_report(
            character_name=self.char_name_edit.text(),
            character_setting=self.char_setting_edit.toPlainText(),
            emotion_tags=self.emotion_tags_edit.toPlainText(),
            sample_output=self.template_sample_output_edit.toPlainText(),
            preflight=self._build_template_preflight_report(),
        )

    def _generate_template_publish_handoff_report(self):
        level, message = self._build_template_publish_handoff_report()
        self._set_template_validation_result(message, level=level)

    def _get_save_file_name(self, *args, **kwargs) -> str:
        path, _ = QFileDialog.getSaveFileName(*args, **kwargs)
        return path

    def _get_existing_directory(self, *args, **kwargs) -> str:
        return QFileDialog.getExistingDirectory(*args, **kwargs)

    def _template_library_root(self) -> Path:
        return Path("data/templates/packages")

    def _filtered_template_library_summaries(self) -> list[TemplatePackageSummary]:
        self.template_library_workflow.refresh(
            search_text=self.template_library_search_edit.text().strip() if hasattr(self, "template_library_search_edit") else "",
            filter_text=self.template_library_filter_combo.currentText() if hasattr(self, "template_library_filter_combo") else "全部",
            sort_text=self.template_library_sort_combo.currentText() if hasattr(self, "template_library_sort_combo") else "按时间（新到旧）",
            preflight_filter_text=self.template_library_preflight_filter_combo.currentText() if hasattr(self, "template_library_preflight_filter_combo") else "全部",
            time_filter_text=self.template_library_time_filter_combo.currentText() if hasattr(self, "template_library_time_filter_combo") else "全部",
        )
        return self.template_library_workflow.visible_summaries

    def _set_template_library_result_summary(self, summaries: list[TemplatePackageSummary]) -> None:
        search_text = self.template_library_search_edit.text().strip() if hasattr(self, "template_library_search_edit") else ""
        filter_text = self.template_library_filter_combo.currentText() if hasattr(self, "template_library_filter_combo") else "全部"
        preflight_filter_text = self.template_library_preflight_filter_combo.currentText() if hasattr(self, "template_library_preflight_filter_combo") else "全部"
        time_filter_text = self.template_library_time_filter_combo.currentText() if hasattr(self, "template_library_time_filter_combo") else "全部"
        text = TemplateSettingsController.template_library_result_summary_text(
            summaries,
            search_text=search_text,
            filter_text=filter_text,
            preflight_filter_text=preflight_filter_text,
            time_filter_text=time_filter_text,
        )
        self.template_library_result_summary_label.setText(text)

    def _reset_template_library_filters(self) -> None:
        self.template_library_search_edit.setText("")
        self.template_library_filter_combo.setCurrentText("全部")
        self.template_library_preflight_filter_combo.setCurrentText("全部")
        self.template_library_time_filter_combo.setCurrentText("全部")
        self.template_library_sort_combo.setCurrentText("按时间（新到旧）")
        self._refresh_template_library()

    def _refresh_template_library(self) -> None:
        search_text = self.template_library_search_edit.text().strip() if hasattr(self, "template_library_search_edit") else ""
        state = self.template_library_workflow.refresh(
            search_text=search_text,
            filter_text=self.template_library_filter_combo.currentText() if hasattr(self, "template_library_filter_combo") else "全部",
            sort_text=self.template_library_sort_combo.currentText() if hasattr(self, "template_library_sort_combo") else "按时间（新到旧）",
            preflight_filter_text=self.template_library_preflight_filter_combo.currentText() if hasattr(self, "template_library_preflight_filter_combo") else "全部",
            time_filter_text=self.template_library_time_filter_combo.currentText() if hasattr(self, "template_library_time_filter_combo") else "全部",
        )
        self._template_library_visible_summaries = self.template_library_workflow.visible_summaries
        self.template_library_result_summary_label.setText(state.result_summary)
        self.template_library_list.clear()
        self.template_library_list.addItems(state.rows)
        self.template_library_detail_label.setText(state.detail_text)
        self.template_import_selected_button.setEnabled(state.import_enabled)
        if state.rows:
            self.template_library_list.setCurrentRow(0)

    def _update_template_library_selection(self, row: int) -> None:
        detail_text, import_enabled = self.template_library_workflow.selection_state(row)
        self.template_library_detail_label.setText(detail_text)
        self.template_import_selected_button.setEnabled(import_enabled)

    def _import_selected_template_library_package(self) -> None:
        row = self.template_library_list.currentRow()
        summary, error_message = self.template_library_workflow.import_selection(row)
        if error_message:
            self._set_status_message(error_message, error=True)
            return

        answer = QMessageBox.question(
            self,
            "确认导入",
            TemplateSettingsController.template_library_import_confirmation_message(),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        import_data, _ = self.template_library_workflow.load_import_selection(
            row,
            load_template_import_data,
        )
        completion = self.template_library_workflow.complete_import(
            self,
            import_data,
            validate=lambda: self._validate_template_sample_output() or self.template_validation_result_label.text(),
        )
        self._set_status_message(completion.status_message)

    def _open_template_library_directory(self) -> None:
        self.template_library_workflow.open_library_directory()


    def _safe_template_draft_filename(self, character_name: str) -> str:
        return TemplateSettingsController.safe_template_draft_filename(character_name)

    def _build_template_publish_draft_markdown(self) -> tuple[str, str]:
        _, handoff_report = self._build_template_publish_handoff_report()
        return TemplateSettingsController.build_template_publish_draft_markdown(
            character_name=self.char_name_edit.text(),
            character_setting=self.char_setting_edit.toPlainText(),
            emotion_tags=self.emotion_tags_edit.toPlainText(),
            sample_output=self.template_sample_output_edit.toPlainText(),
            preflight=self._build_template_preflight_report(),
            handoff_report=handoff_report,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    def _export_template_publish_draft(self):
        level, markdown = self._build_template_publish_draft_markdown()
        if level == "error":
            preflight_level, preflight_message = self._build_template_preflight_report()
            self._set_template_validation_result(preflight_message, level=preflight_level)
            cancel_message = f"导出已取消：发布前检查未通过。\n{preflight_message}"
            self._set_status_message(cancel_message, error=True)
            QMessageBox.critical(self, "发布前检查未通过", cancel_message)
            return

        character_name = self.char_name_edit.text().strip()
        default_name = self._safe_template_draft_filename(character_name)
        path = self._get_save_file_name(self, "导出模板发布草稿", default_name, "Markdown 文件 (*.md)")
        if not path:
            self._set_template_validation_result("已取消导出发布草稿。", level="warning")
            self._set_status_message("已取消导出发布草稿。")
            return

        result = self.template_publish_draft_workflow.write(
            path=path,
            markdown=markdown,
            level=level,
        )
        if result.error:
            error_message = result.message
            self._set_template_validation_result(error_message, level="error")
            self._set_status_message(error_message, error=True)
            QMessageBox.critical(self, "导出失败", error_message)
            return

        message = result.message
        self._set_template_validation_result(message, level=level)
        self._set_status_message(message)
        QMessageBox.information(self, "导出完成", message)

    def _template_sample_token_coverage_list(self, sample_output: str) -> list[str]:
        return TemplateSettingsController.template_sample_token_coverage_list(sample_output)

    def _make_template_release_package_dir_name(self, character_name: str) -> str:
        return TemplateSettingsController.make_template_release_package_dir_name(character_name, now=datetime.now)

    def _build_template_release_package_metadata(self, preflight_level: str, preflight_report: str) -> dict:
        return TemplateSettingsController.build_template_release_package_metadata(
            character_name=self.char_name_edit.text(),
            character_setting=self.char_setting_edit.toPlainText(),
            emotion_tags=self.emotion_tags_edit.toPlainText(),
            sample_output=self.template_sample_output_edit.toPlainText(),
            preflight_level=preflight_level,
            exported_at=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        )

    def _build_template_release_package_files(self) -> tuple[str, dict[str, str]]:
        preflight_level, preflight_report = self._build_template_preflight_report()
        _, handoff_report = self._build_template_publish_handoff_report()
        level, _, _, files = self.template_release_artifact_workflow.build(
            character_name=self.char_name_edit.text(),
            character_setting=self.char_setting_edit.toPlainText(),
            emotion_tags=self.emotion_tags_edit.toPlainText(),
            sample_output=self.template_sample_output_edit.toPlainText(),
            preflight_level=preflight_level,
            preflight_report=preflight_report,
            handoff_report=handoff_report,
        )
        return level, files

    def _export_template_release_package(self):
        level, files = self._build_template_release_package_files()
        if level == "error":
            preflight_level, preflight_message = self._build_template_preflight_report()
            self._set_template_validation_result(preflight_message, level=preflight_level)
            cancel_message = f"导出发布包已取消：发布前检查未通过。\n{preflight_message}"
            self._set_status_message(cancel_message, error=True)
            QMessageBox.critical(self, "发布前检查未通过", cancel_message)
            return

        parent_dir = self._get_existing_directory(self, "选择模板发布包导出目录")
        if not parent_dir:
            self._set_template_validation_result("已取消导出发布包。", level="warning")
            self._set_status_message("已取消导出发布包。")
            return

        result = self.template_package_workflow.write(
            action="export",
            root=Path(parent_dir),
            package_name=self._make_template_release_package_dir_name(self.char_name_edit.text().strip()),
            files=files,
            level=level,
        )
        if result.error:
            error_message = result.message
            self._set_template_validation_result(error_message, level="error")
            self._set_status_message(error_message, error=True)
            QMessageBox.critical(self, "导出失败", error_message)
            return

        message = result.message
        self._set_template_validation_result(message, level=level)
        self._set_status_message(message)
        QMessageBox.information(self, "导出完成", message)

    def _save_template_to_library(self):
        level, files = self._build_template_release_package_files()
        if level == "error":
            preflight_level, preflight_message = self._build_template_preflight_report()
            self._set_template_validation_result(preflight_message, level=preflight_level)
            cancel_message = f"保存到模板库已取消：发布前检查未通过。\n{preflight_message}"
            self._set_status_message(cancel_message, error=True)
            QMessageBox.critical(self, "发布前检查未通过", cancel_message)
            return

        library_root = self._template_library_root()
        result = self.template_package_workflow.write(
            action="library",
            root=library_root,
            package_name=self._make_template_release_package_dir_name(self.char_name_edit.text().strip()),
            files=files,
            level=level,
        )
        if result.error:
            error_message = result.message
            self._set_template_validation_result(error_message, level="error")
            self._set_status_message(error_message, error=True)
            QMessageBox.critical(self, "保存失败", error_message)
            return

        message = result.message
        self._set_template_validation_result(message, level=level)
        self._set_status_message(message)
        QMessageBox.information(self, "保存完成", message)

    def _fill_template_sample_output(self):
        text = TemplateSettingsController.build_template_sample_output(
            self.char_name_edit.text(),
            self.template_sample_type_combo.currentText(),
        )
        self.template_sample_output_edit.setPlainText(text)
        self._validate_template_sample_output()

    def _llm_config_status_message(self, *, saved: bool = False) -> tuple[str, bool]:
        return APISettingsController.llm_config_status_message(
            provider=self.llm_provider_combo.currentText(),
            api_key=self.api_key_edit.text(),
            base_url=self.base_url_edit.text(),
            model=self.model_edit.text(),
            saved=saved,
        )

    def _check_llm_config(self):
        status_message, is_error = self._llm_config_status_message()
        self._set_status_message(status_message, error=is_error)
        label = self._api_tab_parts.llm_status_label
        label.setText(status_message)
        label.setStyleSheet(f"color: {COLOR_ERR if is_error else COLOR_OK};")

    def _check_comfyui_connection(self):
        status_message, is_error = APISettingsController.comfyui_connection_status(
            provider=self.t2i_provider_combo.currentText(),
            base_url=self.t2i_api_url_edit.text(),
        )
        self._set_status_message(status_message, error=is_error)
        label = self._api_tab_parts.t2i_status_label
        label.setText(status_message)
        label.setStyleSheet(f"color: {COLOR_ERR if is_error else COLOR_OK};")

    def closeEvent(self, event):
        if not self.update_controller.shutdown():
            from PySide6.QtCore import QTimer
            event.ignore()
            QTimer.singleShot(100, self, self.close)
            return
        if not getattr(self, "_update_exit_prepared", False) and not self.memory_tab.confirm_pending_edits():
            event.ignore()
            return
        if not self.memory_tab.close_service():
            from PySide6.QtCore import QTimer
            event.ignore()
            QTimer.singleShot(100, self, self.close)
            return
        super().closeEvent(event)

    def _load_config(self):
        """从配置加载到 UI 控件"""
        was_loading = self._loading_settings
        self._loading_settings = True
        try:
            load_settings_into_controls(self.config.config, self)
            self._update_t2i_provider_hint(self.t2i_provider_combo.currentText())
            self._update_tts_provider_hint(self.tts_provider_combo.currentText())

            # 角色标签页
            self._refresh_character_list()
            if self.config.characters:
                self.character_list.setCurrentRow(0)
            else:
                self._update_character_detail_visibility(False)

            self.skills_tab.refresh()
        finally:
            self._loading_settings = was_loading

    def _refresh_skill_settings_lists(self) -> None:
        if self.skills_tab is not None:
            self.skills_tab.refresh()

    def _character_card_avatar_text(self, char) -> str:
        return self.character_controller.character_card_avatar_text(char)

    def _character_overview_summary_text(self) -> str:
        return self.character_controller.character_overview_summary_text()

    def _character_card_stats_text(self, char) -> str:
        return self.character_controller.character_card_stats_text(char)

    def _format_emotion_items_for_editor(self, char) -> str:
        return self.character_controller.format_emotion_items_for_editor(char)

    def _emotion_item_values(self, item) -> tuple[str, str, str]:
        return self.character_controller.emotion_item_values(item)

    def _sprite_paths_for_current_character(self) -> list[str]:
        return self.character_controller.sprite_paths_for_current_character()

    def _append_emotion_binding_row(self, item_id: str, label: str, sprite_path: str) -> None:
        self.character_controller.append_emotion_binding_row(item_id, label, sprite_path)

    def _populate_emotion_binding_table(self, char) -> None:
        self.character_controller.populate_emotion_binding_table(char)

    def _add_emotion_binding_row(self) -> None:
        self.character_controller.add_emotion_binding_row()

    def _delete_selected_emotion_binding_row(self) -> None:
        self.character_controller.delete_selected_emotion_binding_row()

    def _fill_default_emotion_bindings(self) -> None:
        self.character_controller.fill_default_emotion_bindings()

    def _refresh_sprite_list_for_character(self, char) -> None:
        self.character_controller.refresh_sprite_list_for_character(char)

    def _refresh_emotion_binding_sprite_combos(self) -> None:
        self.character_controller.refresh_emotion_binding_sprite_combos()

    def _import_sprite_for_emotion_row(self, row: int) -> None:
        if not (self.config.characters and 0 <= self._current_character_index < len(self.config.characters)):
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择情绪立绘", "", "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not file_path:
            return
        self.character_controller.add_imported_sprite_to_emotion_row(row, file_path)

    def _collect_emotion_bindings_from_table(self) -> list[dict]:
        return self.character_controller.collect_emotion_bindings_from_table()

    def _detail_avatar_editor_value(self, char) -> str:
        return getattr(char, "avatar", "") or getattr(char, "avatar_path", "")

    def _browse_voice_file(self, target, title: str, file_filter: str) -> None:
        current = target.text().strip()
        start_dir = str(Path(current).parent) if current else ""
        file_path, _ = QFileDialog.getOpenFileName(self, title, start_dir, file_filter)
        if file_path:
            target.setText(file_path)
            self._mark_settings_dirty()

    def _browse_refer_audio(self) -> None:
        self._browse_voice_file(
            self.refer_audio_path_edit,
            "\u9009\u62e9\u53c2\u8003\u97f3\u9891",
            "Audio (*.wav *.mp3 *.flac *.ogg *.m4a);;All files (*)",
        )

    def _clear_gpt_sovits_voice(self) -> None:
        self.refer_audio_path_edit.clear()
        self.prompt_text_edit.clear()
        self.prompt_lang_combo.setCurrentText("zh")
        self.speech_speed_spin.setValue(1.0)

    def _import_avatar_for_current_character(self) -> None:
        if not (self.config.characters and 0 <= self._current_character_index < len(self.config.characters)):
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择角色头像", "", "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if file_path:
            self.character_controller.update_avatar_editor(file_path)
            self._mark_settings_dirty()

    def _clear_avatar_for_current_character(self) -> None:
        if not (self.config.characters and 0 <= self._current_character_index < len(self.config.characters)):
            return
        self.character_controller.update_avatar_editor("")
        self._mark_settings_dirty()

    def _show_character_overview_page(self) -> None:
        self.character_controller.show_character_overview_page()

    def _show_character_detail_page(self) -> None:
        self.character_controller.show_character_detail_page()

    def _refresh_character_list(self) -> None:
        self.character_controller.refresh_character_list()

    def _open_character_detail(self, index: int) -> None:
        self.character_controller.open_character_detail(index)

    def _update_character_detail_visibility(self, has_selection: bool) -> None:
        self.character_controller.update_character_detail_visibility(has_selection)

    def _load_character_into_form(self, index: int) -> None:
        self.character_controller.load_character_into_form(index)

    def _on_character_selection_changed(self, row: int) -> None:
        self.character_controller.handle_character_selection_changed(row)

    def _import_sprites_for_current_character(self) -> None:
        if not (self.config.characters and 0 <= self._current_character_index < len(self.config.characters)):
            return
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择角色立绘", "", "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not files:
            return
        self.character_controller.import_sprite_paths_for_current_character(files)

    def _update_sprite_actions(self) -> None:
        selected = bool(self.sprite_list.selectedItems())
        self.preview_sprite_button.setEnabled(selected)
        self.delete_sprite_button.setEnabled(selected)

    def _preview_selected_sprite(self) -> None:
        item = self.sprite_list.currentItem()
        if item is None:
            return
        from ui.settings_ui.sprite_preview import SpritePreviewDialog
        try:
            dialog = SpritePreviewDialog(str(item.data(Qt.ItemDataRole.UserRole) or ""), self)
        except ValueError as exc:
            self._set_status_message(str(exc), error=True)
            return
        dialog.open()

    def _delete_selected_sprite(self) -> None:
        item = self.sprite_list.currentItem()
        if item is None:
            return
        from ui.settings_ui.dialogs import confirm
        from ui.settings_ui.image_preview import image_preview
        selected_path = str(item.data(Qt.ItemDataRole.UserRole) or "")
        bindings = self.character_controller.collect_emotion_bindings_from_table()
        affected = [str(binding.get("label", "")) for binding in bindings
                    if self.character_controller._binding_matches_sprite(str(binding.get("sprite_path", "")), selected_path)]
        detail = "受影响的情绪：" + ("、".join(affected) if affected else "没有情绪绑定这张立绘")
        if not confirm(self, "删除选中立绘？", "删除后会解除对应情绪绑定。保存配置后清理未使用的项目副本，原始导入文件保留。",
                       detail=detail, thumbnail=image_preview(selected_path, QSize(110, 150)),
                       action="删除立绘", destructive=True):
            return
        path = self.character_controller.delete_selected_sprite()
        if path is not None:
            self.character_overview_summary_label.setText(self._character_overview_summary_text())
            index = self._current_character_index
            if 0 <= index < len(self.character_card_stats_labels):
                self.character_card_stats_labels[index].setText(self._character_card_stats_text(self.config.characters[index]))
            self._set_status_message("已移除选中立绘；保存配置后生效。相关情绪可重新选择或导入图片。")

    def _add_character(self) -> None:
        existing = {character.name for character in self.config.characters}
        name = "新角色"
        suffix = 2
        while name in existing:
            name = f"新角色 {suffix}"
            suffix += 1
        self.character_controller.add_character(name)
        self.character_tab.header_title.setText("新建角色")
        self.character_tab.detail_tabs.setCurrentIndex(0)
        self.char_name_edit.setFocus()
        self.char_name_edit.selectAll()
        self._mark_settings_dirty()
        self._set_status_message("正在编辑新角色，保存配置后写入。")

    def _add_skill_preset(self) -> None:
        if self.skills_tab is not None:
            self.skills_tab._add_skill_preset()

    def _character_sprite_dir(self, character_name: str) -> Path:
        return self.character_controller.character_sprite_dir(character_name)

    def _archive_character_sprites(self, character_name: str, sprites: list) -> list[dict]:
        return self.character_controller.archive_character_sprites(character_name, sprites)

    def _archive_character_avatar(self, character_name: str, avatar_path: str) -> str:
        return self.character_controller.archive_character_avatar(character_name, avatar_path)

    def _rename_skill_preset(self) -> None:
        if self.skills_tab is not None:
            self.skills_tab._rename_skill_preset()

    def _delete_skill_preset(self) -> None:
        if self.skills_tab is not None:
            self.skills_tab._delete_skill_preset()

    def set_character_switch_managed(self, managed: bool) -> None:
        """The embedded runtime owns the active ID until it saves the old session."""
        self._character_switch_managed = bool(managed)
        self.character_controller.refresh_character_use_buttons()

    def set_active_character_id(self, character_id: str) -> None:
        self._active_character_id = str(character_id or "")
        self.character_controller.refresh_character_use_buttons()

    def set_character_switch_enabled(self, enabled: bool) -> None:
        self._character_switch_enabled = bool(enabled)
        self.character_controller.refresh_character_use_buttons()

    def _use_character(self, character_id: str) -> None:
        if not self._character_switch_enabled or character_id == self._active_character_id:
            return
        if not any(character.memory_id == character_id for character in self.config.characters):
            return
        previous_id = getattr(self.config.system_config, "active_character_id", "")
        # A standalone settings EXE persists the next startup selection. Embedded
        # settings leave this field to the runtime so it can first save the old
        # character's session under its original identity.
        if not self._character_switch_managed:
            self.config.system_config.active_character_id = character_id
        if not self._save_config(silent=True):
            if not self._character_switch_managed:
                self.config.system_config.active_character_id = previous_id
            return
        if not self._character_switch_managed:
            self.set_active_character_id(character_id)
            self._set_status_message("● 已选择聊天角色，下次打开主界面时生效")
        self.character_selected.emit(character_id)

    def _save_config(self, _checked=False, *, silent: bool = False) -> bool:
        """从 UI 控件写回配置并保存"""
        try:
            background_path = str(self.background_path_combo.currentData() or "")
            if background_path:
                from PySide6.QtGui import QImageReader
                source = Path(background_path)
                if not source.is_absolute():
                    source = Path("data/backgrounds") / source
                reader = QImageReader(str(source))
                reader.setAutoTransform(True)
                if reader.read().isNull():
                    raise ValueError("背景图片无法读取，请重新选择图片，或选择“无背景”。")
            result = self.template_save_workflow.run(
                preflight=lambda: self._build_template_preflight_report(require_sample_output=False),
                save=lambda: save_settings_from_controls(
                    self.config,
                    self,
                    current_character_index=self._current_character_index,
                    collect_emotion_bindings=self._collect_emotion_bindings_from_table,
                    archive_character_sprites=self._archive_character_sprites,
                    archive_character_avatar=self._archive_character_avatar,
                    removed_sprite_paths=tuple(self.character_controller.pending_removed_sprite_paths),
                ),
                saved_status=lambda: self._llm_config_status_message(saved=True),
            )
            self._set_template_validation_result(
                result.preflight_message,
                level=result.preflight_level,
            )
            self._set_status_message(result.status_message, error=result.is_error)
            if not result.saved:
                QMessageBox.critical(self, "发布前检查未通过", result.status_message)
                return False
            self.character_controller.pending_removed_sprite_paths.clear()
            motion.apply_system_config(self.config.system_config)
            self._settings_dirty = False
            self.background_changed.emit(self.config.system_config.background_path)
            self.always_on_top_changed.emit(self.config.system_config.always_on_top)
            current_index = self._current_character_index
            self._refresh_character_list()
            if 0 <= current_index < len(self.config.characters):
                self.character_list.setCurrentRow(current_index)
            if not silent:
                QMessageBox.information(self, "配置已保存", result.status_message)
            return True

        except Exception as e:
            error_message = f"保存失败: {e}"
            self._set_status_message(error_message, error=True)
            QMessageBox.critical(self, "错误", error_message)
            return False
