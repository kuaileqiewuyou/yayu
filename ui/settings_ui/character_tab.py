from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QTableWidget, QTextEdit, QVBoxLayout, QWidget, QTabWidget, QHeaderView

from ui.settings_ui.controls import NoWheelDoubleSpinBox, SafeComboBox
from ui.settings_ui.presentation import FlowLayout, ResponsiveColumns, ResponsiveFields, scroll_content, release_layout, row_widget, hint, card
from ui.settings_ui.list_cards import SceneGalleryDelegate, CardListDelegate


class CharacterTabParts:
    def __init__(self, widget: QScrollArea, **kwargs):
        self.widget = widget
        for key, value in kwargs.items():
            setattr(self, key, value)


class ResponsiveCharacterGrid(QWidget):
    width_changed = Signal(int)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.width_changed.emit(event.size().width())


class CharacterPageStack(QStackedWidget):
    def minimumSizeHint(self):
        # The overview's card height must not enlarge the independently scrolling editor.
        return QSize(0, 0)

    def hasHeightForWidth(self):
        return self.currentIndex() == 0 and super().hasHeightForWidth()

    def heightForWidth(self, width):
        return super().heightForWidth(width) if self.currentIndex() == 0 else -1


def build_character_tab(window: Any) -> CharacterTabParts:
    scroll = QScrollArea()
    scroll.setObjectName("character_tab_scroll_area")
    scroll.setAccessibleName("Character tab")
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    widget = QWidget()
    widget.setMinimumWidth(0)
    scroll.setWidget(widget)
    layout = QVBoxLayout(widget)

    character_stack = CharacterPageStack()
    character_stack.setObjectName("character_stack")
    character_stack.setAccessibleName("Character management pages")
    character_stack.setMinimumWidth(0)
    character_stack.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
    character_overview_page = QWidget()
    character_overview_page.setObjectName("character_overview_page")
    character_overview_page.setAccessibleName("Character overview page")
    character_overview_page_layout = QVBoxLayout(character_overview_page)
    character_detail_page = QWidget()
    character_detail_page.setObjectName("character_detail_page")
    character_detail_page.setAccessibleName("Character detail page")
    character_detail_page_layout = QVBoxLayout(character_detail_page)

    overview_header_layout = QHBoxLayout()
    character_overview_title_label = QLabel("角色管理")
    character_overview_title_label.setObjectName("character_overview_title_label")
    character_overview_title_label.setAccessibleName("Character overview title")
    character_overview_title_label.setProperty("role", "heading")
    character_overview_summary_label = QLabel("")
    character_overview_summary_label.setObjectName("character_overview_summary_label")
    character_overview_summary_label.setAccessibleName("Character overview summary")
    character_overview_summary_label.setWordWrap(True)
    character_overview_summary_label.setProperty("role", "muted")
    overview_header_layout.addWidget(character_overview_title_label)
    overview_header_layout.addStretch()
    overview_header_layout.addWidget(character_overview_summary_label)
    character_overview_page_layout.addLayout(overview_header_layout)

    character_overview_group = QGroupBox("角色列表")
    character_overview_layout = QVBoxLayout(character_overview_group)

    character_card_grid = ResponsiveCharacterGrid()
    character_card_grid_layout = QGridLayout(character_card_grid)
    character_card_grid_layout.setContentsMargins(0, 0, 0, 0)
    character_card_grid_layout.setHorizontalSpacing(12)
    character_card_grid_layout.setVerticalSpacing(12)
    character_card_grid_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    character_overview_layout.addWidget(character_card_grid)

    character_list = QListWidget()
    character_list.setObjectName("character_list")
    character_list.setAccessibleName("Character list")
    character_list.hide()
    character_overview_layout.addWidget(character_list)

    role_button_layout = QHBoxLayout()
    add_character_button = QPushButton("新增角色")
    add_character_button.setObjectName("add_character_button")
    add_character_button.setAccessibleName("Add character")
    add_character_button.setProperty("role", "primary")
    role_button_layout.addWidget(add_character_button)
    role_button_layout.addStretch()
    character_overview_layout.addLayout(role_button_layout)
    character_overview_page_layout.addWidget(character_overview_group)
    character_overview_page_layout.addStretch()

    detail_nav_layout = QHBoxLayout()
    return_character_list_button = QPushButton("← 返回角色列表")
    return_character_list_button.setObjectName("return_character_list_button")
    return_character_list_button.setAccessibleName("Return to character list")
    detail_nav_layout.addWidget(return_character_list_button)
    detail_nav_layout.addStretch()
    character_detail_page_layout.addLayout(detail_nav_layout)

    character_detail_group = QGroupBox("当前角色详情")
    character_detail_layout = QVBoxLayout(character_detail_group)
    character_empty_state_label = QLabel("请选择一个角色以查看和编辑详情。")
    character_empty_state_label.setWordWrap(True)
    character_detail_layout.addWidget(character_empty_state_label)

    character_detail_content_widget = QWidget()
    character_detail_content_layout = QVBoxLayout(character_detail_content_widget)
    character_detail_content_layout.setContentsMargins(0, 0, 0, 0)
    character_detail_layout.addWidget(character_detail_content_widget)
    character_detail_page_layout.addWidget(character_detail_group)

    basics_group = QGroupBox("角色基础信息")
    basics_layout = QVBoxLayout(basics_group)

    char_name_edit = QLineEdit()
    char_name_edit.setObjectName("character_name_input")
    char_name_edit.setAccessibleName("Character name")
    char_name_edit.setPlaceholderText("例如：小芽")
    basics_layout.addWidget(QLabel("角色名称"))
    basics_layout.addWidget(char_name_edit)

    char_default_skills_edit = QLineEdit()
    char_default_skills_edit.setObjectName("character_default_skills_input")
    char_default_skills_edit.setAccessibleName("Character default skills")
    char_default_skills_edit.setPlaceholderText("例如：romance-dialogue, mystery-foreshadowing")
    basics_layout.addWidget(QLabel("角色默认 Skills（逗号分隔）:"))
    basics_layout.addWidget(char_default_skills_edit)

    char_setting_edit = QTextEdit()
    char_setting_edit.setObjectName("character_setting_input")
    char_setting_edit.setAccessibleName("Character setting")
    char_setting_edit.setPlaceholderText("在此编辑角色设定...")
    basics_layout.addWidget(QLabel("角色设定"))
    basics_layout.addWidget(char_setting_edit)

    emotion_tags_edit = QTextEdit()
    emotion_tags_edit.setObjectName("emotion_tags_input")
    emotion_tags_edit.setAccessibleName("Emotion tags")
    emotion_tags_edit.setMaximumHeight(120)
    emotion_tags_edit.setPlaceholderText("情绪标签，如：0: neutral\n1: happy\n...")
    emotion_tags_label = QLabel("情绪编号预览（由下方绑定自动生成）:")
    emotion_tags_label.setObjectName("emotion_tags_label")
    basics_layout.addWidget(emotion_tags_label)
    basics_layout.addWidget(emotion_tags_edit)
    character_detail_content_layout.addWidget(basics_group)

    voice_group = QGroupBox("GPT-SoVITS \u53c2\u8003\u97f3\u9891")
    voice_group.setObjectName("gpt_sovits_voice_group")
    voice_layout = QVBoxLayout(voice_group)

    voice_help_label = QLabel(
        "\u9879\u76ee\u59cb\u7ec8\u4f7f\u7528 9880 API \u5f53\u524d\u5df2\u52a0\u8f7d\u7684\u6a21\u578b\u3002"
        "\u8fd9\u91cc\u53ea\u914d\u7f6e\u5408\u6210\u6240\u9700\u7684\u53c2\u8003\u97f3\u9891\u548c\u5bf9\u5e94\u53f0\u8bcd\u3002"
    )
    voice_help_label.setWordWrap(True)
    voice_layout.addWidget(voice_help_label)

    def add_voice_path_row(label_text: str, object_name: str, accessible_name: str):
        voice_layout.addWidget(QLabel(label_text))
        row = QHBoxLayout()
        edit = QLineEdit()
        edit.setObjectName(object_name)
        edit.setAccessibleName(accessible_name)
        edit.setPlaceholderText("\u672a\u9009\u62e9")
        button = QPushButton("\u9009\u62e9...")
        row.addWidget(edit, 1)
        row.addWidget(button)
        voice_layout.addLayout(row)
        return edit, button

    refer_audio_path_edit, browse_refer_audio_button = add_voice_path_row(
        "\u53c2\u8003\u97f3\u9891 (.wav/.mp3/.flac):",
        "character_refer_audio_path_input",
        "Character reference audio path",
    )

    prompt_text_edit = QTextEdit()
    prompt_text_edit.setObjectName("character_prompt_text_input")
    prompt_text_edit.setAccessibleName("Character reference transcript")
    prompt_text_edit.setPlaceholderText("\u586b\u5199\u53c2\u8003\u97f3\u9891\u4e2d\u5b9e\u9645\u8bf4\u7684\u53f0\u8bcd\uff0c\u5c3d\u91cf\u4e00\u5b57\u4e0d\u5dee")
    prompt_text_edit.setMaximumHeight(90)
    voice_layout.addWidget(QLabel("\u53c2\u8003\u97f3\u9891\u53f0\u8bcd:"))
    voice_layout.addWidget(prompt_text_edit)

    voice_options_row = QHBoxLayout()
    prompt_lang_combo = SafeComboBox()
    prompt_lang_combo.setObjectName("character_prompt_lang_combo")
    prompt_lang_combo.setAccessibleName("Character reference language")
    prompt_lang_combo.addItems(["zh", "ja", "en", "auto", "yue", "ko"])
    voice_options_row.addWidget(QLabel("\u53c2\u8003\u8bed\u79cd:"))
    voice_options_row.addWidget(prompt_lang_combo)

    speech_speed_spin = NoWheelDoubleSpinBox()
    speech_speed_spin.setObjectName("character_speech_speed_spin")
    speech_speed_spin.setAccessibleName("Character speech speed")
    speech_speed_spin.setRange(0.5, 2.0)
    speech_speed_spin.setSingleStep(0.05)
    speech_speed_spin.setDecimals(2)
    speech_speed_spin.setValue(1.0)
    voice_options_row.addWidget(QLabel("\u8bed\u901f:"))
    voice_options_row.addWidget(speech_speed_spin)
    voice_options_row.addStretch()
    voice_layout.addLayout(voice_options_row)

    voice_action_row = QHBoxLayout()
    clear_voice_button = QPushButton("\u6e05\u9664\u53c2\u8003\u97f3\u9891\u914d\u7f6e")
    clear_voice_button.setObjectName("clear_gpt_sovits_voice_button")
    voice_action_row.addWidget(clear_voice_button)
    voice_action_row.addStretch()
    voice_layout.addLayout(voice_action_row)

    character_detail_content_layout.addWidget(voice_group)

    avatar_group = QGroupBox("头像设置")
    avatar_layout = QHBoxLayout(avatar_group)
    avatar_preview_label = QLabel("头像")
    avatar_preview_label.setObjectName("character_avatar_preview")
    avatar_preview_label.setAccessibleName("Character avatar preview")
    avatar_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    avatar_preview_label.setFixedSize(160, 160)
    avatar_preview_label.setStyleSheet(
        "QLabel { border: 1px dashed #BAC8B3; border-radius: 10px; "
        "color: #657169; background: #EFF3E9; }"
    )
    avatar_layout.addWidget(avatar_preview_label)

    avatar_controls_layout = QVBoxLayout()
    avatar_status_label = QLabel("未设置显式头像。")
    avatar_status_label.setObjectName("character_avatar_status")
    avatar_status_label.setAccessibleName("Character avatar status")
    avatar_status_label.setWordWrap(True)
    avatar_controls_layout.addWidget(avatar_status_label)

    avatar_path_edit = QLineEdit()
    avatar_path_edit.setObjectName("character_avatar_path_input")
    avatar_path_edit.setAccessibleName("Character avatar path")
    avatar_path_edit.setReadOnly(True)
    avatar_path_edit.setPlaceholderText("尚未导入显式头像")
    avatar_controls_layout.addWidget(avatar_path_edit)

    avatar_button_layout = QHBoxLayout()
    import_avatar_button = QPushButton("导入头像")
    import_avatar_button.setObjectName("import_avatar_button")
    import_avatar_button.setAccessibleName("Import character avatar")
    clear_avatar_button = QPushButton("清除头像")
    clear_avatar_button.setObjectName("clear_avatar_button")
    clear_avatar_button.setAccessibleName("Clear character avatar")
    avatar_button_layout.addWidget(import_avatar_button)
    avatar_button_layout.addWidget(clear_avatar_button)
    avatar_button_layout.addStretch()
    avatar_controls_layout.addLayout(avatar_button_layout)
    avatar_controls_layout.addStretch()
    avatar_layout.addLayout(avatar_controls_layout, 1)
    character_detail_content_layout.addWidget(avatar_group)

    emotion_binding_group = QGroupBox("情绪 / 立绘绑定")
    emotion_binding_layout = QVBoxLayout(emotion_binding_group)
    emotion_binding_table = QTableWidget(0, 4)
    emotion_binding_table.setObjectName("emotion_binding_table")
    emotion_binding_table.setAccessibleName("Emotion sprite binding table")
    emotion_binding_table.setHorizontalHeaderLabels(["情绪ID", "显示名称", "绑定立绘", "操作"])
    emotion_binding_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    emotion_binding_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    emotion_binding_table.setMinimumHeight(140)
    emotion_binding_layout.addWidget(emotion_binding_table)

    emotion_binding_button_layout = FlowLayout()
    add_emotion_binding_button = QPushButton("新增情绪")
    add_emotion_binding_button.setObjectName("add_emotion_button")
    add_emotion_binding_button.setAccessibleName("Add emotion binding")
    fill_default_emotions_button = QPushButton("填入默认情绪")
    fill_default_emotions_button.setObjectName("fill_default_emotions_button")
    fill_default_emotions_button.setAccessibleName("Fill default emotions")
    delete_emotion_binding_button = QPushButton("删除选中情绪")
    delete_emotion_binding_button.setObjectName("remove_emotion_button")
    delete_emotion_binding_button.setAccessibleName("Remove selected emotion binding")
    emotion_binding_button_layout.addWidget(add_emotion_binding_button)
    emotion_binding_button_layout.addWidget(fill_default_emotions_button)
    emotion_binding_button_layout.addWidget(delete_emotion_binding_button)
    emotion_binding_button_layout.addStretch()
    emotion_binding_layout.addLayout(emotion_binding_button_layout)
    character_detail_content_layout.addWidget(emotion_binding_group)

    sprite_group = QGroupBox("角色立绘包")
    sprite_layout = QVBoxLayout(sprite_group)

    sprite_list = QListWidget()
    sprite_list.setObjectName("sprite_list")
    sprite_list.setAccessibleName("Sprite list")
    sprite_list.setIconSize(QSize(48, 48))
    sprite_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
    sprite_layout.addWidget(sprite_list)
    sprite_help = QLabel("双击立绘可放大预览。删除会解除对应情绪绑定；保存配置后清理不再使用的项目内图片，原始导入文件保留。")
    sprite_help.setWordWrap(True)
    sprite_layout.addWidget(sprite_help)

    sprite_button_layout = FlowLayout()
    import_sprites_button = QPushButton("导入立绘包")
    import_sprites_button.setObjectName("import_sprite_button")
    import_sprites_button.setAccessibleName("Import sprites")
    sprite_button_layout.addWidget(import_sprites_button)
    preview_sprite_button = QPushButton("放大预览")
    preview_sprite_button.setObjectName("preview_sprite_button")
    preview_sprite_button.setAccessibleName("Preview selected sprite")
    preview_sprite_button.setEnabled(False)
    delete_sprite_button = QPushButton("删除选中立绘")
    delete_sprite_button.setObjectName("delete_sprite_button")
    delete_sprite_button.setAccessibleName("Delete selected sprite")
    delete_sprite_button.setEnabled(False)
    sprite_button_layout.addWidget(preview_sprite_button)
    sprite_button_layout.addWidget(delete_sprite_button)
    sprite_button_layout.addStretch()
    sprite_layout.addLayout(sprite_button_layout)
    character_detail_content_layout.addWidget(sprite_group)

    validation_group = QGroupBox("模板示例与发布前检查")
    validation_layout = QVBoxLayout(validation_group)

    validation_layout.addWidget(QLabel("示例输出校验 (JSON-lines，可选):"))
    template_sample_output_edit = QTextEdit()
    template_sample_output_edit.setObjectName("template_sample_output_input")
    template_sample_output_edit.setAccessibleName("Template sample output")
    template_sample_output_edit.setPlaceholderText("粘贴 LLM 示例输出，每行一个 JSON 对象...")
    template_sample_output_edit.setMaximumHeight(140)
    validation_layout.addWidget(template_sample_output_edit)

    sample_button_layout = FlowLayout()
    template_sample_type_combo = SafeComboBox()
    template_sample_type_combo.setObjectName("template_sample_type_combo")
    template_sample_type_combo.setAccessibleName("Template sample type")
    template_sample_type_combo.addItems(["完整示例", "基础对话", "情绪切换示例", "CG 示例", "剧情分支示例", "模板复用示例", "模板修正示例"])
    sample_button_layout.addWidget(QLabel("示例类型:"))
    sample_button_layout.addWidget(template_sample_type_combo)
    template_validate_button = QPushButton("校验示例输出")
    template_validate_button.setObjectName("template_validate_button")
    template_validate_button.setAccessibleName("Validate template sample")
    template_validate_button.clicked.connect(window._validate_template_sample_output)
    template_fill_sample_button = QPushButton("填入示例")
    template_fill_sample_button.setObjectName("template_fill_sample_button")
    template_fill_sample_button.setAccessibleName("Fill template sample")
    template_fill_sample_button.clicked.connect(window._fill_template_sample_output)
    template_preflight_button = QPushButton("发布前检查")
    template_preflight_button.setObjectName("template_preflight_button")
    template_preflight_button.setAccessibleName("Run template preflight")
    template_preflight_button.clicked.connect(window._run_template_preflight_check)
    template_publish_handoff_button = QPushButton("生成发布清单")
    template_publish_handoff_button.setObjectName("template_publish_handoff_button")
    template_publish_handoff_button.setAccessibleName("Generate template publish handoff")
    template_publish_handoff_button.clicked.connect(window._generate_template_publish_handoff_report)
    template_export_draft_button = QPushButton("导出发布草稿")
    template_export_draft_button.setObjectName("template_export_draft_button")
    template_export_draft_button.setAccessibleName("Export template draft")
    template_export_draft_button.clicked.connect(window._export_template_publish_draft)
    template_export_package_button = QPushButton("导出发布包")
    template_export_package_button.setObjectName("template_export_package_button")
    template_export_package_button.setAccessibleName("Export template package")
    template_export_package_button.clicked.connect(window._export_template_release_package)
    template_save_to_library_button = QPushButton("保存到模板库")
    template_save_to_library_button.setObjectName("template_save_to_library_button")
    template_save_to_library_button.setAccessibleName("Save template to library")
    template_save_to_library_button.clicked.connect(window._save_template_to_library)
    template_copy_validation_result_button = QPushButton("复制结果")
    template_copy_validation_result_button.setObjectName("template_copy_validation_result_button")
    template_copy_validation_result_button.setAccessibleName("Copy template validation result")
    template_copy_validation_result_button.clicked.connect(window._copy_template_validation_result)
    sample_button_layout.addWidget(template_validate_button)
    sample_button_layout.addWidget(template_fill_sample_button)
    sample_button_layout.addWidget(template_preflight_button)
    sample_button_layout.addWidget(template_publish_handoff_button)
    sample_button_layout.addWidget(template_export_draft_button)
    sample_button_layout.addWidget(template_export_package_button)
    sample_button_layout.addWidget(template_save_to_library_button)
    sample_button_layout.addWidget(template_copy_validation_result_button)
    sample_button_layout.addStretch()
    validation_layout.addLayout(sample_button_layout)

    template_validation_result_label = QLabel("")
    template_validation_result_label.setWordWrap(True)
    validation_layout.addWidget(template_validation_result_label)
    character_detail_content_layout.addWidget(validation_group)

    library_group = QGroupBox("本地模板库")
    library_layout = QVBoxLayout(library_group)
    library_button_layout = FlowLayout()
    template_refresh_library_button = QPushButton("刷新模板库")
    template_refresh_library_button.setObjectName("template_refresh_library_button")
    template_refresh_library_button.setAccessibleName("Refresh template library")
    template_refresh_library_button.clicked.connect(window._refresh_template_library)
    template_import_selected_button = QPushButton("导入选中模板")
    template_import_selected_button.setObjectName("template_import_selected_button")
    template_import_selected_button.setAccessibleName("Import selected template")
    template_import_selected_button.clicked.connect(window._import_selected_template_library_package)
    template_import_selected_button.setEnabled(False)
    template_import_selected_button.setToolTip("请先刷新模板库并选择一个可导入模板。")
    template_open_library_button = QPushButton("打开模板库目录")
    template_open_library_button.setObjectName("template_open_library_button")
    template_open_library_button.setAccessibleName("Open template library directory")
    template_open_library_button.clicked.connect(window._open_template_library_directory)
    library_button_layout.addWidget(template_refresh_library_button)
    library_button_layout.addWidget(template_import_selected_button)
    library_button_layout.addWidget(template_open_library_button)
    library_button_layout.addStretch()
    library_layout.addLayout(library_button_layout)

    template_library_search_edit = QLineEdit()
    template_library_search_edit.setObjectName("template_library_search_input")
    template_library_search_edit.setAccessibleName("Template library search")
    template_library_search_edit.setPlaceholderText("搜索本地模板（按角色名过滤）")
    template_library_search_edit.textChanged.connect(window._refresh_template_library)
    library_layout.addWidget(template_library_search_edit)

    template_library_filter_combo = SafeComboBox()
    template_library_filter_combo.setObjectName("template_library_filter_combo")
    template_library_filter_combo.setAccessibleName("Template library filter")
    template_library_filter_combo.addItems(["全部", "只看可导入", "只看不可导入"])
    template_library_filter_combo.currentTextChanged.connect(window._refresh_template_library)
    library_layout.addWidget(template_library_filter_combo)

    template_library_result_summary_label = QLabel("")
    template_library_result_summary_label.setWordWrap(True)
    library_layout.addWidget(template_library_result_summary_label)

    template_library_sort_combo = SafeComboBox()
    template_library_sort_combo.setObjectName("template_library_sort_combo")
    template_library_sort_combo.setAccessibleName("Template library sort")
    template_library_sort_combo.addItems(["按时间（新到旧）", "按名称"])
    template_library_sort_combo.currentTextChanged.connect(window._refresh_template_library)
    library_layout.addWidget(template_library_sort_combo)

    template_library_preflight_filter_combo = SafeComboBox()
    template_library_preflight_filter_combo.setObjectName("template_library_preflight_filter_combo")
    template_library_preflight_filter_combo.setAccessibleName("Template preflight filter")
    template_library_preflight_filter_combo.addItems(["全部", "只看通过", "只看有警告"])
    template_library_preflight_filter_combo.currentTextChanged.connect(window._refresh_template_library)
    library_layout.addWidget(template_library_preflight_filter_combo)

    template_library_time_filter_combo = SafeComboBox()
    template_library_time_filter_combo.setObjectName("template_library_time_filter_combo")
    template_library_time_filter_combo.setAccessibleName("Template time filter")
    template_library_time_filter_combo.addItems(["全部", "最近 1 天"])
    template_library_time_filter_combo.currentTextChanged.connect(window._refresh_template_library)
    library_layout.addWidget(template_library_time_filter_combo)

    template_library_clear_filters_button = QPushButton("清空筛选")
    template_library_clear_filters_button.setObjectName("template_library_clear_filters_button")
    template_library_clear_filters_button.setAccessibleName("Clear template library filters")
    template_library_clear_filters_button.clicked.connect(window._reset_template_library_filters)
    library_layout.addWidget(template_library_clear_filters_button)

    template_library_list = QListWidget()
    template_library_list.setObjectName("template_library_list")
    template_library_list.setAccessibleName("Template library list")
    template_library_list.currentRowChanged.connect(window._update_template_library_selection)
    library_layout.addWidget(template_library_list)

    template_library_detail_label = QLabel("暂无本地模板。")
    template_library_detail_label.setWordWrap(True)
    library_layout.addWidget(template_library_detail_label)
    character_detail_content_layout.addWidget(library_group)

    # Keep the existing editor objects and signals; only change their presentation.
    detail_tabs = QTabWidget()
    detail_tabs.setObjectName("character_detail_tabs")
    detail_tabs.setAccessibleName("Character detail sections")
    detail_tabs.setMinimumHeight(280)
    while character_detail_content_layout.count():
        character_detail_content_layout.takeAt(0)
    character_detail_content_layout.addWidget(detail_tabs)

    def add_section(title, groups, tabs=detail_tabs):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 12, 0, 0)
        box.setSpacing(14)
        for group in groups:
            box.addWidget(group)
        box.addStretch()
        tabs.addTab(scroll_content(page), title)

    add_section("基本信息", [ResponsiveColumns([basics_group, avatar_group], breakpoint=900)])
    add_section("立绘与情绪", [ResponsiveColumns([sprite_group, emotion_binding_group], breakpoint=900)])
    add_section("声音", [voice_group])
    template_tabs = QTabWidget()
    template_tabs.setObjectName("character_template_tabs")
    # Validation, results and exporting are separate steps in the reference.
    release_layout(validation_layout)
    validation_group.setTitle("示例输出")
    validation_layout.addWidget(row_widget([QLabel("示例类型"), template_sample_type_combo, template_fill_sample_button], stretch=True))
    template_sample_output_edit.setMaximumHeight(300)
    template_sample_output_edit.setMinimumHeight(180)
    validation_layout.addWidget(template_sample_output_edit)
    validation_layout.addWidget(row_widget([template_validate_button, template_preflight_button], stretch=True))
    results_group, results_layout = card("检查结果")
    template_validation_result_label.setText("尚未检查。填入示例后，可校验输出并运行发布前检查。")
    results_layout.addWidget(row_widget([template_validation_result_label, template_copy_validation_result_button]))
    export_widget = QWidget()
    export_layout = FlowLayout(export_widget)
    for button in (template_publish_handoff_button, template_export_draft_button, template_export_package_button, template_save_to_library_button):
        export_layout.addWidget(button)
    for control in (template_sample_type_combo, template_fill_sample_button, template_sample_output_edit,
                    template_validate_button, template_preflight_button, template_validation_result_label,
                    template_copy_validation_result_button, template_publish_handoff_button,
                    template_export_draft_button, template_export_package_button, template_save_to_library_button):
        control.show()
    add_section("校验与导出", [validation_group, results_group, export_widget], template_tabs)

    release_layout(library_layout)
    library_group.setTitle("")
    library_group.setProperty("role", "plain")
    library_layout.setContentsMargins(0, 0, 0, 0)
    library_layout.addWidget(row_widget([template_refresh_library_button, template_import_selected_button, template_open_library_button], stretch=True))
    library_layout.addWidget(ResponsiveFields([
        ("搜索模板", template_library_search_edit), ("导入状态", template_library_filter_combo),
        ("排序", template_library_sort_combo), ("检查结果", template_library_preflight_filter_combo),
        ("更新时间", template_library_time_filter_combo), ("", template_library_clear_filters_button),
    ], columns=3, breakpoint=750))
    library_layout.addWidget(template_library_result_summary_label)
    library_detail_group, library_detail = card("模板详情")
    library_detail.addWidget(template_library_detail_label)
    library_detail.addStretch()
    template_library_list.setProperty("role", "cards")
    template_library_list.setWordWrap(True)
    template_library_list.setItemDelegate(CardListDelegate(template_library_list))
    template_library_list.setMinimumHeight(260)
    library_layout.addWidget(ResponsiveColumns([template_library_list, library_detail_group], breakpoint=750))
    for control in (template_refresh_library_button, template_import_selected_button, template_open_library_button,
                    template_library_search_edit, template_library_filter_combo, template_library_sort_combo,
                    template_library_preflight_filter_combo, template_library_time_filter_combo,
                    template_library_clear_filters_button, template_library_result_summary_label,
                    template_library_list, template_library_detail_label):
        control.show()
    add_section("本地模板库", [library_group], template_tabs)
    detail_tabs.addTab(template_tabs, "模板与导入")
    char_setting_edit.setMinimumHeight(160)
    sprite_list.setMinimumHeight(315)
    sprite_list.setViewMode(QListWidget.ViewMode.IconMode)
    sprite_list.setResizeMode(QListWidget.ResizeMode.Adjust)
    sprite_list.setMovement(QListWidget.Movement.Static)
    sprite_list.setIconSize(QSize(100, 235))
    sprite_list.setGridSize(QSize(120, 286))
    sprite_list.setWordWrap(True)
    sprite_list.setUniformItemSizes(True)
    sprite_list.setItemDelegate(SceneGalleryDelegate(sprite_list, sprites=True))
    emotion_binding_table.verticalHeader().hide()
    emotion_binding_table.verticalHeader().setDefaultSectionSize(62)
    emotion_binding_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    emotion_binding_table.setMinimumHeight(315)
    emotion_binding_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    emotion_binding_table.horizontalHeader().resizeSection(0, 62)
    template_library_list.setMinimumHeight(160)
    for button in (delete_sprite_button, delete_emotion_binding_button, clear_avatar_button, clear_voice_button):
        button.setProperty("role", "danger")
    for button in (import_sprites_button, template_validate_button, template_import_selected_button):
        button.setProperty("role", "primary")
    # Let the inner page scroll; the tab strip and back button remain accessible.
    character_stack.setMinimumHeight(0)
    layout.setContentsMargins(28, 24, 28, 24)
    character_overview_page_layout.setContentsMargins(0, 0, 0, 0)
    character_overview_page_layout.setSpacing(20)
    character_overview_group.setTitle("")
    character_overview_group.setProperty("role", "plain")
    character_overview_layout.setContentsMargins(0, 0, 0, 0)
    overview_header_layout.removeWidget(character_overview_summary_label)
    role_button_layout.removeWidget(add_character_button)
    overview_header_layout.addWidget(add_character_button)
    character_overview_page_layout.insertWidget(1, character_overview_summary_label)
    character_detail_group.setTitle("")
    character_detail_group.setProperty("role", "plain")
    character_detail_layout.setContentsMargins(0, 0, 0, 0)
    character_detail_page_layout.setSpacing(20)
    release_layout(detail_nav_layout)
    header_title = QLabel("角色管理")
    header_title.setProperty("role", "heading")
    header_subtitle = hint("管理角色设定、立绘与情绪绑定。")
    header_text = QWidget()
    header_box = QVBoxLayout(header_text)
    header_box.setContentsMargins(0, 0, 0, 0)
    header_box.addWidget(header_title)
    header_box.addWidget(header_subtitle)
    header_avatar = QLabel()
    header_avatar.setFixedSize(64, 64)
    header_name = QLabel()
    header_name.setProperty("role", "character-name")
    switch_character = SafeComboBox()
    switch_character.setObjectName("switch_character_combo")
    switch_character.setMinimumWidth(135)
    switch_character.setAccessibleName("选择要编辑的角色")
    switch_character.setToolTip("选择要编辑的角色；开始聊天请在角色卡片点击“使用此角色”")
    detail_nav_layout.addWidget(header_text, 1)
    detail_nav_layout.addWidget(header_avatar)
    detail_nav_layout.addWidget(header_name)
    detail_nav_layout.addWidget(return_character_list_button)
    detail_nav_layout.addWidget(switch_character)
    return_character_list_button.setText("返回角色列表")
    return_character_list_button.show()
    avatar_group.setTitle("角色头像")
    avatar_preview_label.setFixedSize(200, 290)
    avatar_controls_layout.setSpacing(16)
    avatar_button_layout.removeWidget(import_avatar_button)
    avatar_button_layout.removeWidget(clear_avatar_button)
    release_layout(avatar_button_layout)
    avatar_controls_layout.removeItem(avatar_button_layout)
    avatar_controls_layout.addWidget(import_avatar_button)
    avatar_controls_layout.addWidget(clear_avatar_button)
    avatar_controls_layout.addStretch()
    avatar_status_label.setProperty("role", "notice")
    prompt_text_edit.setMaximumHeight(180)
    prompt_text_edit.setMinimumHeight(110)
    voice_layout.setSpacing(18)
    speech_speed_spin.setFixedWidth(140)
    emotion_tags_edit.setMaximumHeight(90)
    emotion_chips = QWidget()
    chips_layout = FlowLayout(emotion_chips)
    basics_layout.addWidget(emotion_chips)
    def refresh_emotion_chips(*_):
        while chips_layout.count():
            item = chips_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        has_bindings = emotion_binding_table.rowCount() > 0
        emotion_tags_edit.setVisible(not has_bindings)
        emotion_chips.setVisible(has_bindings)
        for row in range(emotion_binding_table.rowCount()):
            number, name = emotion_binding_table.item(row, 0), emotion_binding_table.item(row, 1)
            label = QLabel(f"{number.text() if number else ''}：{name.text() if name else ''}")
            label.setProperty("role", "badge")
            chips_layout.addWidget(label)
    detail_tabs.currentChanged.connect(refresh_emotion_chips)
    for index in reversed(range(avatar_controls_layout.count())):
        if avatar_controls_layout.itemAt(index).spacerItem():
            avatar_controls_layout.takeAt(index)
    avatar_controls_layout.addStretch()
    switch_character.activated.connect(lambda index: window._open_character_detail(index))
    character_detail_page_layout.setContentsMargins(0, 0, 0, 0)
    character_stack.addWidget(character_overview_page)
    character_stack.addWidget(character_detail_page)
    layout.addWidget(character_stack)

    return CharacterTabParts(
        scroll,
        character_stack=character_stack,
        detail_tabs=detail_tabs,
        template_tabs=template_tabs,
        header_title=header_title,
        header_avatar=header_avatar,
        header_name=header_name,
        switch_character=switch_character,
        refresh_emotion_chips=refresh_emotion_chips,
        character_overview_page=character_overview_page,
        character_detail_page=character_detail_page,
        return_character_list_button=return_character_list_button,
        character_overview_title_label=character_overview_title_label,
        character_overview_summary_label=character_overview_summary_label,
        character_overview_group=character_overview_group,
        character_card_grid=character_card_grid,
        character_card_grid_layout=character_card_grid_layout,
        character_detail_group=character_detail_group,
        character_empty_state_label=character_empty_state_label,
        character_detail_content_widget=character_detail_content_widget,
        character_detail_content_layout=character_detail_content_layout,
        character_card_placeholder_text="头像",
        character_list=character_list,
        add_character_button=add_character_button,
        char_name_edit=char_name_edit,
        char_default_skills_edit=char_default_skills_edit,
        char_setting_edit=char_setting_edit,
        voice_group=voice_group,
        voice_help_label=voice_help_label,
        refer_audio_path_edit=refer_audio_path_edit,
        browse_refer_audio_button=browse_refer_audio_button,
        prompt_text_edit=prompt_text_edit,
        prompt_lang_combo=prompt_lang_combo,
        speech_speed_spin=speech_speed_spin,
        clear_voice_button=clear_voice_button,
        avatar_group=avatar_group,
        avatar_preview_label=avatar_preview_label,
        avatar_status_label=avatar_status_label,
        avatar_path_edit=avatar_path_edit,
        import_avatar_button=import_avatar_button,
        clear_avatar_button=clear_avatar_button,
        emotion_tags_edit=emotion_tags_edit,
        emotion_tags_label=emotion_tags_label,
        emotion_binding_table=emotion_binding_table,
        add_emotion_binding_button=add_emotion_binding_button,
        fill_default_emotions_button=fill_default_emotions_button,
        delete_emotion_binding_button=delete_emotion_binding_button,
        sprite_list=sprite_list,
        import_sprites_button=import_sprites_button,
        preview_sprite_button=preview_sprite_button,
        delete_sprite_button=delete_sprite_button,
        template_sample_output_edit=template_sample_output_edit,
        template_sample_type_combo=template_sample_type_combo,
        template_validate_button=template_validate_button,
        template_fill_sample_button=template_fill_sample_button,
        template_preflight_button=template_preflight_button,
        template_publish_handoff_button=template_publish_handoff_button,
        template_export_draft_button=template_export_draft_button,
        template_export_package_button=template_export_package_button,
        template_save_to_library_button=template_save_to_library_button,
        template_copy_validation_result_button=template_copy_validation_result_button,
        template_validation_result_label=template_validation_result_label,
        template_refresh_library_button=template_refresh_library_button,
        template_import_selected_button=template_import_selected_button,
        template_open_library_button=template_open_library_button,
        template_library_search_edit=template_library_search_edit,
        template_library_filter_combo=template_library_filter_combo,
        template_library_result_summary_label=template_library_result_summary_label,
        template_library_sort_combo=template_library_sort_combo,
        template_library_preflight_filter_combo=template_library_preflight_filter_combo,
        template_library_time_filter_combo=template_library_time_filter_combo,
        template_library_clear_filters_button=template_library_clear_filters_button,
        template_library_list=template_library_list,
        template_library_detail_label=template_library_detail_label,
    )
