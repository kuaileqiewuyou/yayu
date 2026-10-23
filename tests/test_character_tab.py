import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.settings_ui.character_tab import build_character_tab


def _app():
    return QApplication.instance() or QApplication([])


class _FakeWindow:
    def _validate_template_sample_output(self):
        pass

    def _fill_template_sample_output(self):
        pass

    def _run_template_preflight_check(self):
        pass

    def _generate_template_publish_handoff_report(self):
        pass

    def _export_template_publish_draft(self):
        pass

    def _export_template_release_package(self):
        pass

    def _save_template_to_library(self):
        pass

    def _copy_template_validation_result(self):
        pass

    def _refresh_template_library(self, *args, **kwargs):
        pass

    def _import_selected_template_library_package(self):
        pass

    def _open_template_library_directory(self):
        pass

    def _reset_template_library_filters(self):
        pass

    def _update_template_library_selection(self, *args, **kwargs):
        pass


def test_build_character_tab_exposes_expected_widgets():
    _app()
    parts = build_character_tab(_FakeWindow())

    assert parts.widget is not None
    assert parts.character_list is not None
    assert parts.add_character_button.text() == "新增角色"
    assert parts.sprite_list is not None
    assert parts.import_sprites_button.text() == "导入立绘包"
    assert parts.preview_sprite_button.text() == "放大预览"
    assert parts.delete_sprite_button.text() == "删除选中立绘"
    assert not parts.preview_sprite_button.isEnabled()
    assert not parts.delete_sprite_button.isEnabled()
    assert parts.char_name_edit.placeholderText() == "例如：小芽"
    assert parts.char_default_skills_edit.placeholderText() == "例如：romance-dialogue, mystery-foreshadowing"
    assert parts.template_preflight_button.text() == "发布前检查"
    assert parts.template_library_list is not None
    assert parts.template_library_detail_label.text() == "暂无本地模板。"


def test_build_character_tab_exposes_card_overview_and_detail_regions():
    _app()
    parts = build_character_tab(_FakeWindow())

    assert parts.character_overview_group.property("role") == "plain"
    assert parts.character_card_grid is not None
    assert parts.character_detail_group.property("role") == "plain"
    assert parts.character_empty_state_label.text() == "请选择一个角色以查看和编辑详情。"


def test_build_character_tab_exposes_avatar_preview_slot_in_character_cards():
    _app()
    parts = build_character_tab(_FakeWindow())

    assert parts.character_card_placeholder_text == "头像"


def test_build_character_tab_exposes_explicit_avatar_editor_in_character_detail():
    _app()
    parts = build_character_tab(_FakeWindow())

    assert parts.avatar_group.title() == "角色头像"
    assert parts.avatar_preview_label.objectName() == "character_avatar_preview"
    assert parts.avatar_path_edit.objectName() == "character_avatar_path_input"
    assert parts.avatar_path_edit.isReadOnly()
    assert parts.import_avatar_button.text() == "导入头像"
    assert parts.clear_avatar_button.text() == "清除头像"
    assert parts.avatar_status_label.wordWrap()


def test_build_character_tab_places_template_tools_inside_character_detail_group():
    _app()
    parts = build_character_tab(_FakeWindow())

    detail_children = parts.character_detail_group.findChildren(type(parts.template_validation_result_label))
    assert parts.template_validation_result_label in detail_children
    assert parts.template_library_list.parent() is not None
    assert parts.template_library_list.parent().parent() is not None
    assert parts.character_detail_content_widget.isAncestorOf(parts.template_library_list)
    assert parts.template_tabs.count() == 2


def test_build_character_tab_exposes_gpt_sovits_reference_controls():
    _app()
    parts = build_character_tab(_FakeWindow())

    assert parts.voice_group.objectName() == "gpt_sovits_voice_group"
    assert parts.refer_audio_path_edit.objectName() == "character_refer_audio_path_input"
    assert parts.prompt_text_edit.objectName() == "character_prompt_text_input"
    assert parts.prompt_lang_combo.objectName() == "character_prompt_lang_combo"
    assert [parts.prompt_lang_combo.itemText(i) for i in range(parts.prompt_lang_combo.count())] == [
        "zh", "ja", "en", "auto", "yue", "ko",
    ]
    assert parts.speech_speed_spin.objectName() == "character_speech_speed_spin"
    assert parts.speech_speed_spin.minimum() == 0.5
    assert parts.speech_speed_spin.maximum() == 2.0
    assert parts.clear_voice_button.objectName() == "clear_gpt_sovits_voice_button"
