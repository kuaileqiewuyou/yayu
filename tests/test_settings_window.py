import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import URLError

import pytest
import yaml
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QSizePolicy

from config.config_manager import ConfigManager
from core.security.allowed_roots import AllowedRootsStore
from tts.tts_adapter import TTSAdapterFactory
from ui.settings_ui.window import SettingsWindow
from ui.settings_ui.daylight import COLOR_OK, COLOR_WARN, COLOR_ERR


DEFAULT_CHARACTER = {
    "name": "小雪",
    "color": "#87CEEB",
    "character_setting": "诺艾尔人格设定",
    "emotion_tags": "0: neutral",
    "sprites": [],
    "emotion_items": [],
}


def fake_message_recorder(calls):
    def _record(parent=None, title=None, text=None, *args, **kwargs):
        if title is None:
            title = kwargs.get("title")
        if text is None:
            text = kwargs.get("text")
        calls.append({"title": title, "text": text})

    return _record


def set_valid_template_preflight(window, *, character_name="小雪"):
    window.char_name_edit.setText(character_name)
    window.char_setting_edit.setPlainText("认真可靠的见习骑士，负责陪伴玩家完成日常对话。")
    window.emotion_tags_edit.setPlainText("0: neutral\n1: happy")
    window.template_sample_output_edit.setPlainText(
        json.dumps(
            {"character_name": character_name, "speech": "我会认真帮你准备好的。", "sprite": "0"},
            ensure_ascii=False,
        )
        + "\n"
    )


def _template_sample_lines(window):
    return [json.loads(line) for line in window.template_sample_output_edit.toPlainText().splitlines() if line.strip()]


def _template_sample_character_names(window):
    return [line["character_name"] for line in _template_sample_lines(window)]


@pytest.fixture
def settings_config(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    paths = {
        "api": tmp_path / "api.yaml",
        "api_local": tmp_path / "api.local.yaml",
        "system": tmp_path / "system_config.yaml",
        "characters": tmp_path / "characters.yaml",
        "background": tmp_path / "background.yaml",
        "mcp": tmp_path / "mcp.yaml",
    }
    monkeypatch.setattr(ConfigManager, "_API_CONFIG_PATH", paths["api"])
    monkeypatch.setattr(ConfigManager, "_API_LOCAL_CONFIG_PATH", paths["api_local"])
    monkeypatch.setattr(ConfigManager, "_SYSTEM_CONFIG_PATH", paths["system"])
    monkeypatch.setattr(ConfigManager, "_CHARACTERS_CONFIG_PATH", paths["characters"])
    monkeypatch.setattr(ConfigManager, "_BACKGROUND_CONFIG_PATH", paths["background"])
    monkeypatch.setattr(ConfigManager, "_MCP_CONFIG_PATH", paths["mcp"])

    def write_config(api=None, system=None, characters=None, background=None):
        if characters is None:
            characters = [DEFAULT_CHARACTER]
        if background is None:
            background = []

        paths["api"].write_text(yaml.safe_dump(api or {}, allow_unicode=True), encoding="utf-8")
        paths["system"].write_text(yaml.safe_dump(system or {}, allow_unicode=True), encoding="utf-8")
        paths["characters"].write_text(yaml.safe_dump(characters, allow_unicode=True), encoding="utf-8")
        paths["background"].write_text(yaml.safe_dump(background, allow_unicode=True), encoding="utf-8")
        ConfigManager.reset()
        return paths

    yield write_config
    ConfigManager.reset()


@pytest.fixture
def make_settings_window(tmp_path):
    app = QApplication.instance() or QApplication([])
    windows = []

    def _make():
        window = SettingsWindow(allowed_roots_store=AllowedRootsStore(tmp_path / "roots.json", project_root=tmp_path))
        windows.append(window)
        return window

    yield _make

    for window in windows:
        window.close()
        window.deleteLater()
    app.processEvents()
    ConfigManager.reset()

def test_settings_window_validates_template_sample_output_success(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()

    window.template_sample_output_edit.setPlainText('{"character_name":"小雪","speech":"你好","sprite":"0"}\n')
    window._validate_template_sample_output()

    assert "示例输出校验通过" in window.template_validation_result_label.text()
    assert COLOR_OK in window.template_validation_result_label.styleSheet()
    assert window.template_validation_result_label.toolTip() == window.template_validation_result_label.text()


def test_settings_titlebar_uses_the_window_application_icon(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()

    assert not window.windowIcon().isNull()
    assert window.settings_app_icon.objectName() == "settings_app_icon"
    assert window.settings_app_icon.pixmap().toImage() == window.windowIcon().pixmap(24, 24).toImage()


def test_switching_character_keeps_editor_drafts_without_writing_files(settings_config, make_settings_window):
    paths = settings_config(characters=[DEFAULT_CHARACTER, {**DEFAULT_CHARACTER, "name": "第二位角色"}])
    before = paths["characters"].read_bytes()
    window = make_settings_window()
    window._open_character_detail(0)
    window.char_setting_edit.setPlainText("尚未保存的人设修改")
    window.char_name_edit.setText("新的名字")
    window._open_character_detail(1)
    window._open_character_detail(0)
    assert window.char_setting_edit.toPlainText() == "尚未保存的人设修改"
    assert window.char_name_edit.text() == "新的名字"
    assert paths["characters"].read_bytes() == before


def test_new_character_opens_full_editor_with_unique_name(settings_config, make_settings_window):
    paths = settings_config(characters=[{**DEFAULT_CHARACTER, "name": "新角色"}])
    before = paths["characters"].read_bytes()
    window = make_settings_window()
    window._add_character()
    assert window.character_stack.currentWidget() is window.character_detail_page
    assert window.char_name_edit.text() == "新角色 2"
    assert window.character_tab.detail_tabs.currentIndex() == 0
    assert paths["characters"].read_bytes() == before


def test_sprite_delete_confirmation_cancels_without_mutation(settings_config, make_settings_window, monkeypatch):
    paths = settings_config(characters=[{**DEFAULT_CHARACTER,
        "sprites": [{"id": 0, "path": "portrait.png"}],
        "emotion_items": [{"id": 0, "label": "平静", "sprite_path": "portrait.png"}]}])
    window = make_settings_window()
    window.sprite_list.setCurrentRow(0)
    before = paths["characters"].read_bytes()
    seen = []
    def cancel(*args, **kwargs):
        seen.append(kwargs["detail"])
        return False
    monkeypatch.setattr("ui.settings_ui.dialogs.confirm", cancel)
    window._delete_selected_sprite()
    assert window.sprite_list.count() == 1
    assert not window.character_controller.pending_removed_sprite_paths
    assert "平静" in seen[0]
    assert paths["characters"].read_bytes() == before
    monkeypatch.setattr("ui.settings_ui.dialogs.confirm", lambda *args, **kwargs: True)
    window._delete_selected_sprite()
    assert window.sprite_list.count() == 0
    assert window._collect_emotion_bindings_from_table()[0]["sprite_path"] == ""
    assert paths["characters"].read_bytes() == before


def test_settings_navigation_respects_independent_memory_save(settings_config, make_settings_window, monkeypatch):
    settings_config()
    window = make_settings_window()
    window.settings_nav.setCurrentRow(8)
    assert window.save_settings_button.isHidden()
    window.settings_nav.setCurrentRow(9)
    assert window.save_settings_button.isHidden()
    window.memory_tab.content.setPlainText("未保存的记忆")
    def keep_editing(dialog):
        next(button for button in dialog.buttons() if button.text() == "继续编辑").click()
        return 0
    monkeypatch.setattr(QMessageBox, "exec", keep_editing)
    window.settings_nav.setCurrentRow(0)
    assert window.settings_tabs.currentIndex() == 9
    assert window.settings_nav.currentRow() == 9
    assert window.memory_tab.content.toPlainText() == "未保存的记忆"
    window.memory_tab.dirty = False
    window.settings_nav.setCurrentRow(0)
    assert not window.save_settings_button.isHidden()


def test_settings_window_validates_template_sample_output_errors(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()

    window.template_sample_output_edit.setPlainText('{"character_name":"小雪","speech":"你好"}\n')
    window._validate_template_sample_output()

    message = window.template_validation_result_label.text()
    assert "示例输出有错误" in message
    assert "第 1 行" in message
    assert "sprite" in message
    assert COLOR_ERR in window.template_validation_result_label.styleSheet()


def test_settings_window_validates_template_sample_output_warnings(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()

    window.template_sample_output_edit.setPlainText('{"character_name":"CG","speech":"","sprite":"夕阳下的教室"}\n')
    window._validate_template_sample_output()

    message = window.template_validation_result_label.text()
    assert "示例输出可用，但有警告" in message
    assert "第 1 行" in message
    assert "CG 的 prompt 应放在 speech" in message
    assert COLOR_ERR not in window.template_validation_result_label.styleSheet()


def test_settings_window_template_sample_validation_requires_text(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()

    window.template_sample_output_edit.setPlainText("   \n")
    window._validate_template_sample_output()

    assert "请先粘贴一段示例输出" in window.template_validation_result_label.text()
    assert COLOR_ERR in window.template_validation_result_label.styleSheet()


def test_settings_window_template_validation_button_runs_validation(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()

    window.template_sample_output_edit.setPlainText('{"character_name":"小雪","speech":"你好","sprite":"0"}\n')
    window.template_validate_button.click()

    assert "示例输出校验通过" in window.template_validation_result_label.text()


def test_settings_window_template_validation_button_runs_validation_after_sample_change(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()

    window.template_sample_output_edit.setPlainText('{"character_name":"小雪","speech":"你好","sprite":"0"}\n')
    window.template_validate_button.click()

    assert "示例输出校验通过" in window.template_validation_result_label.text()


def test_settings_window_template_preflight_button_exists_and_passes(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()
    set_valid_template_preflight(window, character_name="诺艾尔")

    assert window.template_preflight_button.text() == "发布前检查"
    window.template_preflight_button.click()

    message = window.template_validation_result_label.text()
    assert "发布前检查通过" in message
    assert "角色名称：诺艾尔" in message
    assert "示例输出：1 行" in message
    assert "修复建议：" not in message
    assert "建议继续生成发布清单或导出发布包" in message
    assert "如需写入角色配置，请记得点击“保存配置”" in message
    assert COLOR_OK in window.template_validation_result_label.styleSheet()
    assert window.template_validation_result_label.toolTip() == message


def test_settings_window_template_preflight_reports_blocking_errors(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()
    window.char_name_edit.setText("   ")
    window.char_setting_edit.setPlainText("可靠助手")
    window.emotion_tags_edit.setPlainText("0: neutral")
    window.template_sample_output_edit.setPlainText('{"character_name":"诺艾尔","speech":"你好"}\n')

    window._run_template_preflight_check()

    message = window.template_validation_result_label.text()
    assert "发布前检查未通过" in message
    assert "角色名称不能为空" in message
    assert "第 1 行" in message
    assert "sprite" in message
    assert COLOR_ERR in window.template_validation_result_label.styleSheet()


def test_settings_window_template_preflight_errors_include_fix_suggestions(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()
    window.char_name_edit.setText("   ")
    window.char_setting_edit.setPlainText("可靠助手")
    window.emotion_tags_edit.setPlainText("0: neutral")
    window.template_sample_output_edit.setPlainText('{"character_name":"诺艾尔","speech":"你好"}\n')

    window._run_template_preflight_check()

    message = window.template_validation_result_label.text()
    assert "发布前检查未通过" in message
    assert "修复建议：" in message
    assert "填写角色名称，例如：诺艾尔" in message
    assert "补齐对应 JSON 对象的必填字段，例如 sprite" in message
    assert "点击“填入示例”生成一份可用 JSON-lines 后再修改" in message
    assert "优先先修错误，再回头处理警告" in message
    assert "重新点击“发布前检查”确认状态是否变为“通过”或“有警告”" in message


def test_settings_window_template_preflight_requires_sample_output(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()
    window.char_name_edit.setText("诺艾尔")
    window.char_setting_edit.setPlainText("认真可靠的见习骑士，负责陪伴玩家完成日常对话。")
    window.emotion_tags_edit.setPlainText("0: neutral")
    window.template_sample_output_edit.setPlainText("  \n")

    window._run_template_preflight_check()

    message = window.template_validation_result_label.text()
    assert "发布前检查未通过" in message
    assert "请先点击“填入示例”或粘贴 JSON-lines 示例输出" in message
    assert "示例输出：0 行" in message
    assert COLOR_ERR in window.template_validation_result_label.styleSheet()


def test_settings_window_template_preflight_reports_warnings_without_error_style(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()
    window.char_name_edit.setText("诺艾尔")
    window.char_setting_edit.setPlainText("可靠")
    window.emotion_tags_edit.setPlainText("   ")
    window.template_sample_output_edit.setPlainText(
        '{"character_name":"CG","speech":"","sprite":"夕阳下的教室"}\n'
    )

    window._run_template_preflight_check()

    message = window.template_validation_result_label.text()
    assert "发布前检查可用，但有警告" in message
    assert "角色设定较短" in message
    assert "情绪标签为空" in message
    assert "CG 的 prompt 应放在 speech" in message
    assert COLOR_WARN in window.template_validation_result_label.styleSheet()
    assert COLOR_ERR not in window.template_validation_result_label.styleSheet()


def test_settings_window_template_preflight_warnings_include_fix_suggestions(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()
    window.char_name_edit.setText("诺艾尔")
    window.char_setting_edit.setPlainText("可靠")
    window.emotion_tags_edit.setPlainText("   ")
    window.template_sample_output_edit.setPlainText(
        '{"character_name":"CG","speech":"","sprite":"夕阳下的教室"}\n'
    )

    window._run_template_preflight_check()

    message = window.template_validation_result_label.text()
    assert "发布前检查可用，但有警告" in message
    assert "修复建议：" in message
    assert "补充角色性格、称呼方式和对话边界" in message
    assert "补充情绪标签，例如：0: neutral" in message
    assert "把 CG prompt 放到 speech，并将 sprite 设为 \"-1\"" in message
    assert "补齐对应 JSON 对象的必填字段，例如 sprite" not in message
    assert "如果暂时不修，也建议在分享给 reviewer 前至少再复查一次" in message
    assert "重新点击“发布前检查”确认警告是否减少" in message


def test_settings_window_template_preflight_warns_when_character_setting_empty(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()
    window.char_name_edit.setText("诺艾尔")
    window.char_setting_edit.setPlainText("   ")
    window.emotion_tags_edit.setPlainText("0: neutral")
    window.template_sample_output_edit.setPlainText(
        '{"character_name":"诺艾尔","speech":"我会认真帮你准备好的。","sprite":"0"}\n'
    )

    window._run_template_preflight_check()

    message = window.template_validation_result_label.text()
    assert "发布前检查可用，但有警告" in message
    assert "角色设定为空" in message
    assert COLOR_WARN in window.template_validation_result_label.styleSheet()
    assert COLOR_ERR not in window.template_validation_result_label.styleSheet()


def test_settings_window_template_preflight_report_can_be_copied(settings_config, make_settings_window, monkeypatch):
    settings_config()
    window = make_settings_window()
    copied = []
    monkeypatch.setattr(window, "_set_clipboard_text", copied.append)
    window.char_name_edit.setText("诺艾尔")
    window.char_setting_edit.setPlainText("认真可靠的见习骑士，负责陪伴玩家完成日常对话。")
    window.emotion_tags_edit.setPlainText("0: neutral")
    window.template_sample_output_edit.setPlainText(
        '{"character_name":"诺艾尔","speech":"我会认真帮你准备好的。","sprite":"0"}\n'
    )

    window._run_template_preflight_check()
    report = window.template_validation_result_label.text()
    window.template_copy_validation_result_button.click()

    assert copied == [report]
    assert "发布前检查通过" in copied[0]
    assert window.template_validation_result_label.text() == report


def test_settings_window_template_preflight_report_is_not_saved_to_character_config(
    settings_config, make_settings_window, monkeypatch
):
    paths = settings_config()
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))
    window = make_settings_window()
    set_valid_template_preflight(window, character_name="诺艾尔")

    window._run_template_preflight_check()
    window._save_config()

    saved = yaml.safe_load(paths["characters"].read_text(encoding="utf-8"))
    dumped = yaml.safe_dump(saved, allow_unicode=True)
    assert "发布前检查" not in dumped
    assert "template_preflight" not in dumped
    assert "template_sample_output" not in saved[0]


def test_settings_window_template_publish_handoff_report_button_exists_and_passes(
    settings_config, make_settings_window
):
    settings_config()
    window = make_settings_window()
    window.char_name_edit.setText("诺艾尔")
    window.char_setting_edit.setPlainText("认真可靠的见习骑士，负责陪伴玩家完成日常对话。")
    window.emotion_tags_edit.setPlainText("0: neutral\n1: happy")
    window.template_sample_type_combo.setCurrentText("完整示例")
    window.template_fill_sample_button.click()

    assert window.template_publish_handoff_button.text() == "生成发布清单"
    window.template_publish_handoff_button.click()

    message = window.template_validation_result_label.text()
    assert "角色模板发布清单" in message
    assert "角色名称：诺艾尔" in message
    assert "角色设定：" in message
    assert "情绪标签：2 行" in message
    assert "示例输出：5 行" in message
    assert "控制 token 覆盖：NARR、CHOICE、STAT、CG" in message
    assert "发布前检查：通过" in message
    assert "发布前检查摘要：" in message
    assert "发布前检查通过" in message
    assert "完整模板市场" in message
    assert "多示例管理" in message
    assert "正式发布工作流" in message
    assert COLOR_OK in window.template_validation_result_label.styleSheet()
    assert window.template_validation_result_label.toolTip() == message


def test_settings_window_template_publish_handoff_report_preserves_warning_level(
    settings_config, make_settings_window
):
    settings_config()
    window = make_settings_window()
    window.char_name_edit.setText("诺艾尔")
    window.char_setting_edit.setPlainText("可靠")
    window.emotion_tags_edit.setPlainText("   ")
    window.template_sample_output_edit.setPlainText(
        '{"character_name":"CG","speech":"","sprite":"夕阳下的教室"}\n'
    )

    window._generate_template_publish_handoff_report()

    message = window.template_validation_result_label.text()
    assert "发布前检查：有警告" in message
    assert "控制 token 覆盖：CG" in message
    assert "情绪标签：0 行" in message
    assert "角色设定较短" in message
    assert "CG 的 prompt 应放在 speech" in message
    assert COLOR_WARN in window.template_validation_result_label.styleSheet()
    assert COLOR_ERR not in window.template_validation_result_label.styleSheet()


def test_settings_window_template_publish_handoff_report_preserves_error_level(
    settings_config, make_settings_window
):
    settings_config()
    window = make_settings_window()
    window.char_name_edit.setText("   ")
    window.char_setting_edit.setPlainText("可靠助手")
    window.emotion_tags_edit.setPlainText("0: neutral")
    window.template_sample_output_edit.setPlainText(
        '{"character_name":"NARR","speech":"旁白","sprite":"-1"}\n'
        '{"character_name":"诺艾尔","speech":"你好"}\n'
    )

    window._generate_template_publish_handoff_report()

    message = window.template_validation_result_label.text()
    assert "角色名称：未填写" in message
    assert "示例输出：2 行" in message
    assert "控制 token 覆盖：NARR" in message
    assert "发布前检查：未通过" in message
    assert "角色名称不能为空" in message
    assert "缺少必填字段" in message
    assert COLOR_ERR in window.template_validation_result_label.styleSheet()


def test_settings_window_template_publish_handoff_report_can_be_copied(
    settings_config, make_settings_window, monkeypatch
):
    settings_config()
    window = make_settings_window()
    copied = []
    monkeypatch.setattr(window, "_set_clipboard_text", copied.append)
    set_valid_template_preflight(window, character_name="诺艾尔")

    window._generate_template_publish_handoff_report()
    report = window.template_validation_result_label.text()
    window.template_copy_validation_result_button.click()

    assert copied == [report]
    assert "角色模板发布清单" in copied[0]
    assert window.template_validation_result_label.text() == report


def test_settings_window_template_publish_handoff_report_is_not_saved_to_character_config(
    settings_config, make_settings_window, monkeypatch
):
    paths = settings_config()
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))
    window = make_settings_window()
    set_valid_template_preflight(window, character_name="诺艾尔")

    window._generate_template_publish_handoff_report()
    window._save_config()

    saved = yaml.safe_load(paths["characters"].read_text(encoding="utf-8"))
    dumped = yaml.safe_dump(saved, allow_unicode=True)
    assert "角色模板发布清单" not in dumped
    assert "template_publish" not in dumped
    assert "template_handoff" not in dumped
    assert "template_sample_output" not in saved[0]


def test_settings_window_template_publish_draft_export_button_writes_markdown(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    target = tmp_path / "noelle-draft.md"
    info_calls = []
    monkeypatch.setattr(window, "_get_save_file_name", lambda *args, **kwargs: str(target))
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))
    window.char_name_edit.setText("诺艾尔")
    window.char_setting_edit.setPlainText("认真可靠的见习骑士，负责陪伴玩家完成日常对话。")
    window.emotion_tags_edit.setPlainText("0: neutral\n1: happy")
    window.template_sample_type_combo.setCurrentText("完整示例")
    window.template_fill_sample_button.click()

    assert window.template_export_draft_button.text() == "导出发布草稿"
    window.template_export_draft_button.click()

    text = target.read_text(encoding="utf-8")
    assert "# 角色模板发布草稿：诺艾尔" in text
    assert "## 角色信息" in text
    assert "角色名称：诺艾尔" in text
    assert "角色设定长度：" in text
    assert "情绪标签行数：2 行" in text
    assert "示例输出行数：5 行" in text
    assert "控制 token 覆盖：NARR、CHOICE、STAT、CG" in text
    assert "发布前检查：通过" in text
    assert "## 角色设定" in text
    assert "认真可靠的见习骑士" in text
    assert "## 情绪标签" in text
    assert "```text" in text
    assert "## 示例输出 JSON-lines" in text
    assert "```jsonl" in text
    assert "## 发布前检查摘要" in text
    assert "发布前检查通过" in text
    assert "## 轻量发布清单" in text
    assert "角色模板发布清单" in text
    assert "## 边界" in text
    assert "完整模板市场" in text
    assert "多示例管理" in text
    assert "正式发布工作流" in text
    message = window.template_validation_result_label.text()
    assert "已导出发布草稿" in message
    assert str(target) in message
    assert window.save_status_label.text() == message
    assert len(info_calls) == 1


class FixedDateTime(datetime):
    @classmethod
    def now(cls):
        return cls(2026, 5, 26, 20, 59, 0)


def test_settings_window_template_release_package_export_button_writes_package_directory(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    parent_dir = tmp_path / "exports"
    parent_dir.mkdir()
    info_calls = []
    monkeypatch.setattr(window, "_get_existing_directory", lambda *args, **kwargs: str(parent_dir))
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))
    window.char_name_edit.setText("诺艾尔")
    window.char_setting_edit.setPlainText("认真可靠的见习骑士，负责陪伴玩家完成日常对话。")
    window.emotion_tags_edit.setPlainText("0: neutral\n1: happy")
    window.template_sample_type_combo.setCurrentText("完整示例")
    window.template_fill_sample_button.click()

    assert window.template_export_package_button.text() == "导出发布包"
    window.template_export_package_button.click()

    packages = list(parent_dir.iterdir())
    assert len(packages) == 1
    package_dir = packages[0]
    assert package_dir.is_dir()
    assert package_dir.name.startswith("诺艾尔-template-package-")

    expected_files = {
        "README.md",
        "角色模板发布草稿.md",
        "template-output.jsonl",
        "preflight-report.txt",
        "metadata.json",
        "template-data.json",
    }
    assert {path.name for path in package_dir.iterdir()} == expected_files

    readme = (package_dir / "README.md").read_text(encoding="utf-8")
    draft = (package_dir / "角色模板发布草稿.md").read_text(encoding="utf-8")
    jsonl = (package_dir / "template-output.jsonl").read_text(encoding="utf-8")
    preflight = (package_dir / "preflight-report.txt").read_text(encoding="utf-8")
    metadata = json.loads((package_dir / "metadata.json").read_text(encoding="utf-8"))
    template_data = json.loads((package_dir / "template-data.json").read_text(encoding="utf-8"))

    assert "# 角色模板发布包：诺艾尔" in readme
    assert "本地轻量模板发布包" in readme
    assert "不是自动发布" in readme
    assert "模板市场" in readme
    assert "多示例管理" in readme
    assert "正式发布工作流" in readme
    assert "- `README.md`" in readme
    assert "template-output.jsonl" in readme
    assert "metadata.json" in readme
    assert "template-data.json" in readme
    assert "# 角色模板发布草稿：诺艾尔" in draft
    assert jsonl.endswith("\n")
    assert '"character_name": "NARR"' in jsonl
    assert "发布前检查通过" in preflight
    assert metadata["schema_version"] == 1
    assert metadata["package_type"] == "galgame_agent.character_template.release_package"
    assert metadata["character_name"] == "诺艾尔"
    assert metadata["preflight_level"] == "ok"
    assert metadata["preflight_status"] == "通过"
    assert metadata["token_coverage"] == ["NARR", "CHOICE", "STAT", "CG"]
    assert metadata["files"] == [
        "README.md",
        "角色模板发布草稿.md",
        "template-output.jsonl",
        "preflight-report.txt",
        "metadata.json",
        "template-data.json",
    ]
    assert metadata["boundaries"] == {
        "local_only": True,
        "contains_private_api_config": False,
        "contains_chat_history": False,
        "is_marketplace_publish": False,
    }
    assert template_data["schema_version"] == 1
    assert template_data["package_type"] == "galgame_agent.character_template.import_data"
    assert template_data["character_name"] == "诺艾尔"
    assert template_data["character_setting"] == "认真可靠的见习骑士，负责陪伴玩家完成日常对话。"
    assert template_data["emotion_tags"] == "0: neutral\n1: happy"
    assert template_data["sample_output"].endswith("\n")
    message = window.template_validation_result_label.text()
    assert "已导出发布包" in message
    assert str(package_dir) in message
    assert window.save_status_label.text() == message
    assert len(info_calls) == 1


def test_settings_window_template_release_package_preserves_raw_jsonl_text(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    parent_dir = tmp_path / "exports"
    parent_dir.mkdir()
    monkeypatch.setattr(window, "_get_existing_directory", lambda *args, **kwargs: str(parent_dir))
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder([]))
    window.char_name_edit.setText("诺艾尔")
    window.char_setting_edit.setPlainText("认真可靠的见习骑士，负责陪伴玩家完成日常对话。")
    window.emotion_tags_edit.setPlainText("0: neutral\n1: happy")
    raw_sample = (
        "\n"
        '  {"character_name":"诺艾尔","speech":"你好","sprite":"0"}  \n'
        "\n"
        '  {"character_name":"NARR","speech":"风吹过窗边。","sprite":"-1"}  '
    )
    window.template_sample_output_edit.setPlainText(raw_sample)

    window._export_template_release_package()

    package_dir = next(parent_dir.iterdir())
    jsonl = (package_dir / "template-output.jsonl").read_text(encoding="utf-8")
    metadata = json.loads((package_dir / "metadata.json").read_text(encoding="utf-8"))
    assert jsonl == raw_sample + "\n"
    assert metadata["sample_output_lines"] == 2


def test_settings_window_template_release_package_dir_name_sanitizes_invalid_characters(
    settings_config, make_settings_window, monkeypatch
):
    settings_config()
    window = make_settings_window()
    monkeypatch.setattr("ui.settings_ui.window.datetime", FixedDateTime)

    assert window._make_template_release_package_dir_name('诺艾尔:/?* "') == "诺艾尔-template-package-2026-05-26-205900"
    assert window._make_template_release_package_dir_name("   ") == "template-package-2026-05-26-205900"


def test_settings_window_template_publish_draft_export_reports_write_failure(
    settings_config, make_settings_window, monkeypatch
):
    settings_config()
    window = make_settings_window()
    critical_calls = []
    monkeypatch.setattr(window, "_get_save_file_name", lambda *args, **kwargs: "C:/blocked/draft.md")

    def fail_write(path, text):
        raise OSError("disk full")

    monkeypatch.setattr(window.template_publish_draft_workflow, "_write_text_file", fail_write)
    monkeypatch.setattr(QMessageBox, "critical", fake_message_recorder(critical_calls))
    set_valid_template_preflight(window, character_name="诺艾尔")

    window._export_template_publish_draft()

    message = window.template_validation_result_label.text()
    assert "导出发布草稿失败" in message
    assert "disk full" in message
    assert window.save_status_label.text() == message
    assert COLOR_ERR in window.template_validation_result_label.styleSheet()
    assert COLOR_ERR in window.save_status_label.styleSheet()
    assert len(critical_calls) == 1
    assert "导出失败" in critical_calls[0]["title"]


def test_settings_window_template_release_package_export_blocks_preflight_errors(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    critical_calls = []
    requested_dirs = []
    monkeypatch.setattr(
        window,
        "_get_existing_directory",
        lambda *args, **kwargs: requested_dirs.append(True) or str(tmp_path),
    )
    monkeypatch.setattr(QMessageBox, "critical", fake_message_recorder(critical_calls))
    window.char_name_edit.setText("   ")
    window.char_setting_edit.setPlainText("可靠助手")
    window.emotion_tags_edit.setPlainText("0: neutral")
    window.template_sample_output_edit.setPlainText('{"character_name":"诺艾尔","speech":"你好"}\n')

    window._export_template_release_package()

    message = window.template_validation_result_label.text()
    assert "发布前检查未通过" in message
    assert "角色名称不能为空" in message
    assert "缺少必填字段" in message
    assert "导出发布包已取消" in window.save_status_label.text()
    assert requested_dirs == []
    exports_dir = tmp_path / "exports"
    assert not exports_dir.exists() or list(exports_dir.iterdir()) == []
    assert len(critical_calls) == 1


def test_settings_window_template_release_package_export_cancel_does_not_write(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    monkeypatch.setattr(window, "_get_existing_directory", lambda *args, **kwargs: "")
    monkeypatch.setattr(
        window.template_package_workflow,
        "_make_directory",
        lambda path: pytest.fail("should not create directory"),
    )
    set_valid_template_preflight(window, character_name="诺艾尔")

    window._export_template_release_package()

    exports_dir = tmp_path / "exports"
    assert not exports_dir.exists() or list(exports_dir.iterdir()) == []
    assert "已取消导出发布包" in window.template_validation_result_label.text()
    assert COLOR_WARN in window.template_validation_result_label.styleSheet()


def test_settings_window_template_release_package_export_allows_warnings_with_notice(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    parent_dir = tmp_path / "exports"
    parent_dir.mkdir()
    monkeypatch.setattr(window, "_get_existing_directory", lambda *args, **kwargs: str(parent_dir))
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder([]))
    window.char_name_edit.setText("诺艾尔")
    window.char_setting_edit.setPlainText("可靠")
    window.emotion_tags_edit.setPlainText("   ")
    window.template_sample_output_edit.setPlainText(
        '{"character_name":"CG","speech":"","sprite":"夕阳下的教室"}\n'
    )

    window._export_template_release_package()

    package_dir = next(parent_dir.iterdir())
    metadata = json.loads((package_dir / "metadata.json").read_text(encoding="utf-8"))
    preflight = (package_dir / "preflight-report.txt").read_text(encoding="utf-8")
    assert metadata["preflight_level"] == "warning"
    assert metadata["preflight_status"] == "有警告"
    assert "角色设定较短" in preflight
    assert "CG 的 prompt 应放在 speech" in preflight
    message = window.template_validation_result_label.text()
    assert "已导出发布包" in message
    assert "发布前检查有警告" in message
    assert COLOR_WARN in window.template_validation_result_label.styleSheet()


def test_settings_window_template_release_package_export_reports_write_failure_and_cleans_directory(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    parent_dir = tmp_path / "exports"
    parent_dir.mkdir()
    critical_calls = []
    monkeypatch.setattr(window, "_get_existing_directory", lambda *args, **kwargs: str(parent_dir))

    def fail_write(path, text):
        if str(path).endswith("README.md"):
            Path(path).write_text(text, encoding="utf-8")
            return
        raise OSError("disk full")

    monkeypatch.setattr(window.template_package_workflow, "_write_text_file", fail_write)
    monkeypatch.setattr(QMessageBox, "critical", fake_message_recorder(critical_calls))
    set_valid_template_preflight(window, character_name="诺艾尔")

    window._export_template_release_package()

    assert list(parent_dir.iterdir()) == []
    message = window.template_validation_result_label.text()
    assert "导出发布包失败" in message
    assert "disk full" in message
    assert COLOR_ERR in window.template_validation_result_label.styleSheet()
    assert len(critical_calls) == 1


def test_settings_window_template_release_package_export_failure_reports_target_when_cleanup_incomplete(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    parent_dir = tmp_path / "exports"
    parent_dir.mkdir()
    critical_calls = []
    monkeypatch.setattr(window, "_get_existing_directory", lambda *args, **kwargs: str(parent_dir))
    monkeypatch.setattr(window, "_make_template_release_package_dir_name", lambda character_name: "noelle-package")

    def fail_write(path, text):
        if str(path).endswith("README.md"):
            Path(path).write_text(text, encoding="utf-8")
            return
        raise OSError("disk full")

    def fail_rmdir(path):
        raise OSError("permission denied")

    monkeypatch.setattr(window.template_package_workflow, "_write_text_file", fail_write)
    monkeypatch.setattr(Path, "rmdir", fail_rmdir)
    monkeypatch.setattr(QMessageBox, "critical", fake_message_recorder(critical_calls))
    set_valid_template_preflight(window, character_name="诺艾尔")

    window._export_template_release_package()

    package_dir = parent_dir / "noelle-package"
    message = window.template_validation_result_label.text()
    assert package_dir.exists()
    assert "导出发布包失败" in message
    assert "disk full" in message
    assert f"目标路径：{package_dir}" in message
    assert window.save_status_label.text() == message
    assert len(critical_calls) == 1
    assert f"目标路径：{package_dir}" in critical_calls[0]["text"]


def test_settings_window_template_release_package_export_privacy_and_non_persistence_boundaries(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    paths = settings_config()
    window = make_settings_window()
    parent_dir = tmp_path / "exports"
    parent_dir.mkdir()
    monkeypatch.setattr(window, "_get_existing_directory", lambda *args, **kwargs: str(parent_dir))
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder([]))
    window.api_key_edit.setText("sk-sec...port")
    window.t2i_api_url_edit.setText("http://127.0.0.1:8000")
    set_valid_template_preflight(window, character_name="诺艾尔")

    window._export_template_release_package()
    window._save_config()

    package_dir = next(parent_dir.iterdir())
    combined = "\n".join(path.read_text(encoding="utf-8") for path in package_dir.iterdir())
    assert "sk-sec...port" not in combined
    assert "llm_api_key" not in combined
    assert "t2i_api_url" not in combined
    assert "api.local.yaml" not in combined
    assert "default.json" not in combined

    saved = yaml.safe_load(paths["characters"].read_text(encoding="utf-8"))
    dumped = yaml.safe_dump(saved, allow_unicode=True)
    assert "角色模板发布包" not in dumped
    assert "template_release_package" not in dumped
    assert "template_sample_output" not in saved[0]


def test_settings_window_template_save_to_library_writes_package_directory(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    info_calls = []
    library_root = tmp_path / "packages"
    monkeypatch.setattr(window, "_template_library_root", lambda: library_root)
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))
    window.char_name_edit.setText("诺艾尔")
    window.char_setting_edit.setPlainText("认真可靠的见习骑士，负责陪伴玩家完成日常对话。")
    window.emotion_tags_edit.setPlainText("0: neutral\n1: happy")
    window.template_sample_type_combo.setCurrentText("完整示例")
    window.template_fill_sample_button.click()

    window._save_template_to_library()

    packages = list(library_root.iterdir())
    assert len(packages) == 1
    package_dir = packages[0]
    assert package_dir.is_dir()
    assert package_dir.name.startswith("诺艾尔-template-package-")
    assert (package_dir / "template-data.json").exists()
    message = window.template_validation_result_label.text()
    assert "已保存到模板库" in message
    assert str(package_dir) in message
    assert window.save_status_label.text() == message
    assert len(info_calls) == 1


def test_settings_window_template_save_to_library_blocks_preflight_errors(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    critical_calls = []
    library_root = tmp_path / "packages"
    monkeypatch.setattr(window, "_template_library_root", lambda: library_root)
    monkeypatch.setattr(QMessageBox, "critical", fake_message_recorder(critical_calls))
    window.char_name_edit.setText("   ")
    window.char_setting_edit.setPlainText("可靠助手")
    window.emotion_tags_edit.setPlainText("0: neutral")
    window.template_sample_output_edit.setPlainText('{"character_name":"诺艾尔","speech":"你好"}\n')

    window._save_template_to_library()

    message = window.template_validation_result_label.text()
    assert "发布前检查未通过" in message
    assert "保存到模板库已取消" in window.save_status_label.text()
    assert not library_root.exists() or list(library_root.iterdir()) == []
    assert len(critical_calls) == 1


def test_settings_window_template_save_to_library_allows_warnings_with_notice(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    info_calls = []
    library_root = tmp_path / "packages"
    monkeypatch.setattr(window, "_template_library_root", lambda: library_root)
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))
    window.char_name_edit.setText("诺艾尔")
    window.char_setting_edit.setPlainText("可靠")
    window.emotion_tags_edit.setPlainText("   ")
    window.template_sample_output_edit.setPlainText(
        '{"character_name":"CG","speech":"","sprite":"夕阳下的教室"}\n'
    )

    window._save_template_to_library()

    package_dir = next(library_root.iterdir())
    metadata = json.loads((package_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["preflight_level"] == "warning"
    message = window.template_validation_result_label.text()
    assert "已保存到模板库" in message
    assert "发布前检查有警告" in message
    assert len(info_calls) == 1


def test_settings_window_template_library_refresh_shows_empty_state(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    library_root = tmp_path / "packages"
    monkeypatch.setattr(window, "_template_library_root", lambda: library_root)

    window._refresh_template_library()

    assert window.template_library_list.count() == 0
    assert "暂无本地模板" in window.template_library_detail_label.text()
    assert "下一步建议：先保存到模板库，或打开模板库目录检查是否有可用发布包" in window.template_library_detail_label.text()
    assert window.template_import_selected_button.isEnabled() is False
    assert window.template_import_selected_button.toolTip() == "请先刷新模板库并选择一个可导入模板。"


def test_settings_window_open_template_library_directory_creates_root_and_opens_url(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    library_root = tmp_path / "packages"
    opened_urls = []

    import ui.settings_ui.window as settings_window_module

    monkeypatch.setattr(window, "_template_library_root", lambda: library_root)
    monkeypatch.setattr(settings_window_module.QDesktopServices, "openUrl", opened_urls.append)

    window._open_template_library_directory()

    assert library_root.exists()
    assert Path(opened_urls[0].toLocalFile()) == library_root.resolve()


def test_settings_window_template_library_refresh_lists_valid_and_invalid_packages(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    library_root = tmp_path / "packages"
    valid_dir = library_root / "valid-package"
    invalid_dir = library_root / "invalid-package"
    another_valid_dir = library_root / "another-valid-package"
    valid_dir.mkdir(parents=True)
    invalid_dir.mkdir(parents=True)
    another_valid_dir.mkdir(parents=True)
    monkeypatch.setattr(window, "_template_library_root", lambda: library_root)
    stale_exported_at = (datetime.now() - timedelta(days=2)).replace(microsecond=0).isoformat()
    recent_exported_at = (datetime.now() - timedelta(hours=1)).replace(microsecond=0).isoformat()

    release_metadata = {
        "schema_version": 1,
        "package_type": "galgame_agent.character_template.release_package",
        "character_name": "诺艾尔",
        "exported_at": stale_exported_at,
        "preflight_level": "ok",
        "preflight_status": "通过",
        "token_coverage": ["NARR", "CHOICE"],
        "files": [
            "README.md",
            "角色模板发布草稿.md",
            "template-output.jsonl",
            "preflight-report.txt",
            "metadata.json",
            "template-data.json",
        ],
        "boundaries": {
            "local_only": True,
            "contains_private_api_config": False,
            "contains_chat_history": False,
            "is_marketplace_publish": False,
        },
    }
    alt_release_metadata = {
        **release_metadata,
        "character_name": "芙宁娜",
        "exported_at": recent_exported_at,
        "preflight_level": "warning",
        "preflight_status": "有警告",
    }
    (valid_dir / "README.md").write_text("# package\n", encoding="utf-8")
    (valid_dir / "角色模板发布草稿.md").write_text(
        "# 角色模板发布草稿：诺艾尔\n\n## 角色设定\n\n认真可靠的见习骑士。\n\n## 情绪标签\n```text\n0: neutral\n1: happy\n```\n\n## 示例输出 JSON-lines\n```jsonl\n{\"character_name\":\"诺艾尔\",\"speech\":\"你好\",\"sprite\":\"0\"}\n```\n",
        encoding="utf-8",
    )
    (valid_dir / "template-output.jsonl").write_text(
        '{"character_name":"诺艾尔","speech":"你好","sprite":"0"}\n',
        encoding="utf-8",
    )
    (valid_dir / "preflight-report.txt").write_text("发布前检查通过\n", encoding="utf-8")
    (valid_dir / "metadata.json").write_text(json.dumps(release_metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (valid_dir / "template-data.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "package_type": "galgame_agent.character_template.import_data",
                "character_name": "诺艾尔",
                "character_setting": "认真可靠的见习骑士。",
                "emotion_tags": "0: neutral\n1: happy",
                "sample_output": '{"character_name":"诺艾尔","speech":"你好","sprite":"0"}\n',
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (another_valid_dir / "README.md").write_text("# package\n", encoding="utf-8")
    (another_valid_dir / "角色模板发布草稿.md").write_text(
        "# 角色模板发布草稿：芙宁娜\n\n## 角色设定\n\n夸张又敏感的舞台型角色。\n\n## 情绪标签\n```text\n0: neutral\n1: proud\n```\n\n## 示例输出 JSON-lines\n```jsonl\n{\"character_name\":\"芙宁娜\",\"speech\":\"看着我吧\",\"sprite\":\"0\"}\n```\n",
        encoding="utf-8",
    )
    (another_valid_dir / "template-output.jsonl").write_text(
        '{"character_name":"芙宁娜","speech":"看着我吧","sprite":"0"}\n',
        encoding="utf-8",
    )
    (another_valid_dir / "preflight-report.txt").write_text("发布前检查通过\n", encoding="utf-8")
    (another_valid_dir / "metadata.json").write_text(json.dumps(alt_release_metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (another_valid_dir / "template-data.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "package_type": "galgame_agent.character_template.import_data",
                "character_name": "芙宁娜",
                "character_setting": "夸张又敏感的舞台型角色。",
                "emotion_tags": "0: neutral\n1: proud",
                "sample_output": '{"character_name":"芙宁娜","speech":"看着我吧","sprite":"0"}\n',
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (invalid_dir / "README.md").write_text("# broken\n", encoding="utf-8")

    window._refresh_template_library()

    assert window.template_library_list.count() == 3
    item_texts = [window.template_library_list.item(index).text() for index in range(window.template_library_list.count())]
    assert any(text.startswith(f"诺艾尔｜可导入｜通过｜NARR/CHOICE｜{stale_exported_at}") for text in item_texts)
    assert window.template_library_search_edit.text() == ""
    assert window.template_library_filter_combo.currentText() == "全部"
    assert window.template_library_sort_combo.currentText() == "按时间（新到旧）"
    assert window.template_library_result_summary_label.text() == "共 3 个模板：2 个可导入，1 个不可导入"
    assert item_texts[0].startswith(f"芙宁娜｜可导入｜有警告｜NARR/CHOICE｜{recent_exported_at}")
    assert item_texts[1].startswith(f"诺艾尔｜可导入｜通过｜NARR/CHOICE｜{stale_exported_at}")

    window.template_library_sort_combo.setCurrentText("按名称")
    sorted_item_texts = [window.template_library_list.item(index).text() for index in range(window.template_library_list.count())]
    assert sorted_item_texts[0].startswith("invalid-package｜")
    assert sorted_item_texts[1].startswith("芙宁娜｜")
    assert sorted_item_texts[2].startswith("诺艾尔｜")

    window.template_library_search_edit.setText("芙宁")
    filtered_item_texts = [window.template_library_list.item(index).text() for index in range(window.template_library_list.count())]
    assert filtered_item_texts == [next(text for text in item_texts if text.startswith("芙宁娜｜"))]
    assert "角色名称：芙宁娜" in window.template_library_detail_label.text()
    assert window.template_library_result_summary_label.text() == "当前筛选结果：1 个模板（可导入 1 个）"

    window.template_library_filter_combo.setCurrentText("只看不可导入")
    assert window.template_library_list.count() == 0
    assert "没有匹配的本地模板" in window.template_library_detail_label.text()
    assert "下一步建议：调整搜索关键词，或清空搜索后重新选择模板" in window.template_library_detail_label.text()
    assert window.template_library_result_summary_label.text() == "当前筛选结果：0 个模板"

    window.template_library_search_edit.setText("")
    filtered_item_texts = [window.template_library_list.item(index).text() for index in range(window.template_library_list.count())]
    assert filtered_item_texts == [next(text for text in item_texts if text.startswith("invalid-package｜"))]
    assert "导入状态：不可导入" in window.template_library_detail_label.text()
    assert window.template_library_result_summary_label.text() == "当前筛选结果：1 个模板（不可导入 1 个）"

    window.template_library_filter_combo.setCurrentText("只看可导入")
    filtered_item_texts = [window.template_library_list.item(index).text() for index in range(window.template_library_list.count())]
    assert len(filtered_item_texts) == 2
    assert all("｜可导入｜" in text for text in filtered_item_texts)
    assert window.template_library_result_summary_label.text() == "当前筛选结果：2 个模板（可导入 2 个）"

    window.template_library_preflight_filter_combo.setCurrentText("只看通过")
    filtered_item_texts = [window.template_library_list.item(index).text() for index in range(window.template_library_list.count())]
    assert filtered_item_texts == [next(text for text in item_texts if text.startswith("诺艾尔｜"))]
    assert window.template_library_result_summary_label.text() == "当前筛选结果：1 个模板（可导入 1 个）"

    window.template_library_preflight_filter_combo.setCurrentText("只看有警告")
    filtered_item_texts = [window.template_library_list.item(index).text() for index in range(window.template_library_list.count())]
    assert filtered_item_texts == [next(text for text in item_texts if text.startswith("芙宁娜｜"))]
    assert "发布前检查：有警告" in window.template_library_detail_label.text()

    window.template_library_clear_filters_button.click()
    assert window.template_library_search_edit.text() == ""
    assert window.template_library_filter_combo.currentText() == "全部"
    assert window.template_library_preflight_filter_combo.currentText() == "全部"
    assert window.template_library_sort_combo.currentText() == "按时间（新到旧）"
    assert window.template_library_list.count() == 3
    assert window.template_library_result_summary_label.text() == "共 3 个模板：2 个可导入，1 个不可导入"

    window.template_library_time_filter_combo.setCurrentText("最近 1 天")
    filtered_item_texts = [window.template_library_list.item(index).text() for index in range(window.template_library_list.count())]
    assert filtered_item_texts == [next(text for text in item_texts if text.startswith("芙宁娜｜"))]
    assert window.template_library_result_summary_label.text() == "当前筛选结果：1 个模板（可导入 1 个）"

    window.template_library_time_filter_combo.setCurrentText("全部")
    window.template_library_preflight_filter_combo.setCurrentText("全部")
    window.template_library_filter_combo.setCurrentText("全部")
    window.template_library_search_edit.setText("不存在")

    assert "没有匹配的本地模板" in window.template_library_detail_label.text()
    assert "下一步建议：调整搜索关键词，或清空搜索后重新选择模板" in window.template_library_detail_label.text()

    window.template_library_search_edit.setText("")
    item_texts = [window.template_library_list.item(index).text() for index in range(window.template_library_list.count())]
    assert len(item_texts) == 3
    for index, text in enumerate(item_texts):
        if text.startswith("诺艾尔｜"):
            window.template_library_list.setCurrentRow(index)
            break
    assert "导入状态：可导入" in window.template_library_detail_label.text()
    assert "控制 token 覆盖：NARR、CHOICE" in window.template_library_detail_label.text()
    assert "下一步建议：可直接导入到当前编辑区，并在保存前重新确认配置" in window.template_library_detail_label.text()

    for index, text in enumerate(item_texts):
        if text.startswith("invalid-package｜"):
            window.template_library_list.setCurrentRow(index)
            break
    assert "导入状态：不可导入" in window.template_library_detail_label.text()
    assert "原因：missing metadata.json" in window.template_library_detail_label.text()
    assert "下一步建议：先补齐缺失文件或重新导出发布包，再回来刷新模板库" in window.template_library_detail_label.text()


def test_settings_window_template_library_import_uses_visible_filtered_selection(
    settings_config, make_settings_window, monkeypatch
):
    settings_config()
    window = make_settings_window()
    visible_summary = type("Summary", (), {"path": Path("visible-package")})()
    hidden_summary = type("Summary", (), {"path": Path("hidden-package")})()
    imported_paths = []

    monkeypatch.setattr(window, "_filtered_template_library_summaries", lambda: [visible_summary])
    monkeypatch.setattr(
        "ui.settings_ui.window.scan_template_packages",
        lambda _root: [hidden_summary],
    )
    monkeypatch.setattr(
        "ui.settings_ui.window.TemplateSettingsController.template_library_import_selection",
        lambda summaries, row: (summaries[row], None),
    )
    monkeypatch.setattr(
        "ui.settings_ui.window.load_template_import_data",
        lambda summary: imported_paths.append(summary) or type(
            "ImportData",
            (),
            {
                "character_name": "可见模板",
                "character_setting": "可见设定",
                "emotion_tags": "0: neutral",
                "sample_output": '{"character_name":"可见模板","speech":"你好","sprite":"0"}\n',
            },
        )(),
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    window.template_library_list.blockSignals(True)
    window.template_library_list.addItem("可见模板")
    window.template_library_list.setCurrentRow(0)
    window.template_library_list.blockSignals(False)
    window.template_library_workflow.visible_summaries = [visible_summary]
    window._template_library_visible_summaries = [visible_summary]
    window._import_selected_template_library_package()

    assert imported_paths == [visible_summary.path]
    assert window.char_name_edit.text() == "可见模板"


def test_settings_window_template_library_import_selected_package_fills_fields_and_validates(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    library_root = tmp_path / "packages"
    package_dir = library_root / "valid-package"
    package_dir.mkdir(parents=True)
    question_calls = []

    def fake_question(parent, title, text, buttons, default_button):
        question_calls.append({"title": title, "text": text})
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(window, "_template_library_root", lambda: library_root)
    monkeypatch.setattr(QMessageBox, "question", fake_question)

    release_metadata = {
        "schema_version": 1,
        "package_type": "galgame_agent.character_template.release_package",
        "character_name": "诺艾尔",
        "exported_at": "2026-06-13T12:00:00",
        "preflight_level": "ok",
        "preflight_status": "通过",
        "token_coverage": ["NARR", "CHOICE"],
        "files": [
            "README.md",
            "角色模板发布草稿.md",
            "template-output.jsonl",
            "preflight-report.txt",
            "metadata.json",
            "template-data.json",
        ],
        "boundaries": {
            "local_only": True,
            "contains_private_api_config": False,
            "contains_chat_history": False,
            "is_marketplace_publish": False,
        },
    }
    (package_dir / "README.md").write_text("# package\n", encoding="utf-8")
    (package_dir / "角色模板发布草稿.md").write_text(
        "# 角色模板发布草稿：诺艾尔\n\n## 角色设定\n\n认真可靠的见习骑士。\n\n## 情绪标签\n```text\n0: neutral\n1: happy\n```\n\n## 示例输出 JSON-lines\n```jsonl\n{\"character_name\":\"诺艾尔\",\"speech\":\"你好\",\"sprite\":\"0\"}\n```\n",
        encoding="utf-8",
    )
    (package_dir / "template-output.jsonl").write_text(
        '{"character_name":"诺艾尔","speech":"你好","sprite":"0"}\n',
        encoding="utf-8",
    )
    (package_dir / "preflight-report.txt").write_text("发布前检查通过\n", encoding="utf-8")
    (package_dir / "metadata.json").write_text(json.dumps(release_metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (package_dir / "template-data.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "package_type": "galgame_agent.character_template.import_data",
                "character_name": "诺艾尔",
                "character_setting": "认真可靠的见习骑士。",
                "emotion_tags": "0: neutral\n1: happy",
                "sample_output": '{"character_name":"诺艾尔","speech":"你好","sprite":"0"}\n',
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    window.char_name_edit.setText("旧名字")
    window.char_setting_edit.setPlainText("旧设定")
    window.emotion_tags_edit.setPlainText("9: old")
    window.template_sample_output_edit.setPlainText('{"character_name":"旧名字","speech":"旧内容","sprite":"9"}\n')

    window._refresh_template_library()
    window.template_library_list.setCurrentRow(0)
    window._import_selected_template_library_package()

    assert len(question_calls) == 1
    assert "角色名称" in question_calls[0]["text"]
    assert "角色设定" in question_calls[0]["text"]
    assert "情绪标签" in question_calls[0]["text"]
    assert "示例输出" in question_calls[0]["text"]
    assert "不会自动保存配置" in question_calls[0]["text"]
    assert "自动重新校验" in question_calls[0]["text"]
    assert window.char_name_edit.text() == "诺艾尔"
    assert window.char_setting_edit.toPlainText() == "认真可靠的见习骑士。"
    assert window.emotion_tags_edit.toPlainText() == "0: neutral\n1: happy"
    assert window.template_sample_output_edit.toPlainText() == '{"character_name":"诺艾尔","speech":"你好","sprite":"0"}\n'
    assert "已导入模板：诺艾尔" in window.save_status_label.text()
    assert "示例输出校验通过" in window.template_validation_result_label.text()
    assert "建议继续点击“保存配置”" in window.save_status_label.text()
    assert "如需交接，也可以继续生成发布清单或导出发布包" in window.save_status_label.text()


def test_settings_window_template_library_import_cancel_keeps_existing_fields(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    library_root = tmp_path / "packages"
    package_dir = library_root / "valid-package"
    package_dir.mkdir(parents=True)
    monkeypatch.setattr(window, "_template_library_root", lambda: library_root)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No)

    release_metadata = {
        "schema_version": 1,
        "package_type": "galgame_agent.character_template.release_package",
        "character_name": "诺艾尔",
        "exported_at": "2026-06-13T12:00:00",
        "preflight_level": "ok",
        "preflight_status": "通过",
        "token_coverage": ["NARR", "CHOICE"],
        "files": [
            "README.md",
            "角色模板发布草稿.md",
            "template-output.jsonl",
            "preflight-report.txt",
            "metadata.json",
            "template-data.json",
        ],
        "boundaries": {
            "local_only": True,
            "contains_private_api_config": False,
            "contains_chat_history": False,
            "is_marketplace_publish": False,
        },
    }
    (package_dir / "README.md").write_text("# package\n", encoding="utf-8")
    (package_dir / "角色模板发布草稿.md").write_text("# 角色模板发布草稿：诺艾尔\n", encoding="utf-8")
    (package_dir / "template-output.jsonl").write_text('{"character_name":"诺艾尔","speech":"你好","sprite":"0"}\n', encoding="utf-8")
    (package_dir / "preflight-report.txt").write_text("发布前检查通过\n", encoding="utf-8")
    (package_dir / "metadata.json").write_text(json.dumps(release_metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (package_dir / "template-data.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "package_type": "galgame_agent.character_template.import_data",
                "character_name": "诺艾尔",
                "character_setting": "认真可靠的见习骑士。",
                "emotion_tags": "0: neutral\n1: happy",
                "sample_output": '{"character_name":"诺艾尔","speech":"你好","sprite":"0"}\n',
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    window.char_name_edit.setText("旧名字")
    window.char_setting_edit.setPlainText("旧设定")
    window.emotion_tags_edit.setPlainText("9: old")
    window.template_sample_output_edit.setPlainText('{"character_name":"旧名字","speech":"旧内容","sprite":"9"}\n')

    window._refresh_template_library()
    window.template_library_list.setCurrentRow(0)
    window._import_selected_template_library_package()

    assert window.char_name_edit.text() == "旧名字"
    assert window.char_setting_edit.toPlainText() == "旧设定"
    assert window.emotion_tags_edit.toPlainText() == "9: old"
    assert window.template_sample_output_edit.toPlainText() == '{"character_name":"旧名字","speech":"旧内容","sprite":"9"}\n'


def test_settings_window_template_library_import_warning_sample_updates_status_message(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    library_root = tmp_path / "packages"
    package_dir = library_root / "warning-package"
    package_dir.mkdir(parents=True)
    monkeypatch.setattr(window, "_template_library_root", lambda: library_root)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    release_metadata = {
        "schema_version": 1,
        "package_type": "galgame_agent.character_template.release_package",
        "character_name": "诺艾尔",
        "exported_at": "2026-06-13T12:00:00",
        "preflight_level": "warning",
        "preflight_status": "有警告",
        "token_coverage": ["CG"],
        "files": [
            "README.md",
            "角色模板发布草稿.md",
            "template-output.jsonl",
            "preflight-report.txt",
            "metadata.json",
            "template-data.json",
        ],
        "boundaries": {
            "local_only": True,
            "contains_private_api_config": False,
            "contains_chat_history": False,
            "is_marketplace_publish": False,
        },
    }
    (package_dir / "README.md").write_text("# package\n", encoding="utf-8")
    (package_dir / "角色模板发布草稿.md").write_text("# 角色模板发布草稿：诺艾尔\n", encoding="utf-8")
    (package_dir / "template-output.jsonl").write_text('{"character_name":"CG","speech":"","sprite":"夕阳下的教室"}\n', encoding="utf-8")
    (package_dir / "preflight-report.txt").write_text("发布前检查有警告\n", encoding="utf-8")
    (package_dir / "metadata.json").write_text(json.dumps(release_metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (package_dir / "template-data.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "package_type": "galgame_agent.character_template.import_data",
                "character_name": "诺艾尔",
                "character_setting": "可靠",
                "emotion_tags": "",
                "sample_output": '{"character_name":"CG","speech":"","sprite":"夕阳下的教室"}\n',
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    window._refresh_template_library()
    window.template_library_list.setCurrentRow(0)
    window._import_selected_template_library_package()

    assert "已导入模板：诺艾尔" in window.save_status_label.text()
    assert "当前示例输出仍有警告" in window.save_status_label.text()
    assert "建议先修正后再保存配置或分享给 reviewer" in window.save_status_label.text()
    assert "示例输出可用，但有警告" in window.template_validation_result_label.text()


def test_settings_window_template_publish_draft_export_blocks_preflight_errors(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    critical_calls = []
    requested_paths = []
    monkeypatch.setattr(
        window,
        "_get_save_file_name",
        lambda *args, **kwargs: requested_paths.append(True) or str(tmp_path / "bad.md"),
    )
    monkeypatch.setattr(QMessageBox, "critical", fake_message_recorder(critical_calls))
    window.char_name_edit.setText("   ")
    window.char_setting_edit.setPlainText("可靠助手")
    window.emotion_tags_edit.setPlainText("0: neutral")
    window.template_sample_output_edit.setPlainText('{"character_name":"诺艾尔","speech":"你好"}\n')

    window._export_template_publish_draft()

    message = window.template_validation_result_label.text()
    assert "发布前检查未通过" in message
    assert "角色名称不能为空" in message
    assert "缺少必填字段" in message
    assert "导出已取消" in window.save_status_label.text()
    assert COLOR_ERR in window.template_validation_result_label.styleSheet()
    assert requested_paths == []
    assert not (tmp_path / "bad.md").exists()
    assert len(critical_calls) == 1


def test_settings_window_template_publish_draft_export_blocks_empty_sample_output(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    critical_calls = []
    requested_paths = []
    monkeypatch.setattr(
        window,
        "_get_save_file_name",
        lambda *args, **kwargs: requested_paths.append(True) or str(tmp_path / "empty-sample.md"),
    )
    monkeypatch.setattr(QMessageBox, "critical", fake_message_recorder(critical_calls))
    window.char_name_edit.setText("诺艾尔")
    window.char_setting_edit.setPlainText("认真可靠的见习骑士，负责陪伴玩家完成日常对话。")
    window.emotion_tags_edit.setPlainText("0: neutral")
    window.template_sample_output_edit.setPlainText("  \n")

    window._export_template_publish_draft()

    message = window.template_validation_result_label.text()
    assert "发布前检查未通过" in message
    assert "请先点击“填入示例”或粘贴 JSON-lines 示例输出" in message
    assert "导出已取消" in window.save_status_label.text()
    assert COLOR_ERR in window.template_validation_result_label.styleSheet()
    assert requested_paths == []
    assert not (tmp_path / "empty-sample.md").exists()
    assert len(critical_calls) == 1


def test_settings_window_template_publish_draft_export_cancel_does_not_write(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    target = tmp_path / "cancelled.md"
    monkeypatch.setattr(window, "_get_save_file_name", lambda *args, **kwargs: "")
    monkeypatch.setattr(
        window.template_publish_draft_workflow,
        "_write_text_file",
        lambda path, text: target.write_text(text, encoding="utf-8"),
    )
    set_valid_template_preflight(window, character_name="诺艾尔")

    window._export_template_publish_draft()

    assert not target.exists()
    assert "已取消导出发布草稿" in window.template_validation_result_label.text()
    assert COLOR_WARN in window.template_validation_result_label.styleSheet()


def test_settings_window_template_publish_draft_export_allows_warnings_with_notice(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    settings_config()
    window = make_settings_window()
    target = tmp_path / "warning-draft.md"
    monkeypatch.setattr(window, "_get_save_file_name", lambda *args, **kwargs: str(target))
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder([]))
    window.char_name_edit.setText("诺艾尔")
    window.char_setting_edit.setPlainText("可靠")
    window.emotion_tags_edit.setPlainText("   ")
    window.template_sample_output_edit.setPlainText(
        '{"character_name":"CG","speech":"","sprite":"夕阳下的教室"}\n'
    )

    window._export_template_publish_draft()

    text = target.read_text(encoding="utf-8")
    assert "发布前检查：有警告" in text
    assert "角色设定较短" in text
    assert "CG 的 prompt 应放在 speech" in text
    message = window.template_validation_result_label.text()
    assert "已导出发布草稿" in message
    assert "发布前检查有警告" in message
    assert COLOR_WARN in window.template_validation_result_label.styleSheet()


def test_settings_window_template_publish_draft_export_is_not_saved_to_character_config(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    paths = settings_config()
    window = make_settings_window()
    target = tmp_path / "noelle-draft.md"
    monkeypatch.setattr(window, "_get_save_file_name", lambda *args, **kwargs: str(target))
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder([]))
    set_valid_template_preflight(window, character_name="诺艾尔")

    window._export_template_publish_draft()
    window._save_config()

    saved = yaml.safe_load(paths["characters"].read_text(encoding="utf-8"))
    dumped = yaml.safe_dump(saved, allow_unicode=True)
    assert target.exists()
    assert "角色模板发布草稿" not in dumped
    assert "publish_draft" not in dumped
    assert "template_export" not in dumped
    assert "template_sample_output" not in saved[0]


def test_settings_window_save_blocks_when_template_preflight_has_errors(
    settings_config, make_settings_window, monkeypatch
):
    paths = settings_config()
    info_calls = []
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))
    monkeypatch.setattr(QMessageBox, "critical", fake_message_recorder(critical_calls))
    window = make_settings_window()
    window.char_name_edit.setText("   ")
    window.char_setting_edit.setPlainText("可靠助手")
    window.emotion_tags_edit.setPlainText("0: neutral")
    window.template_sample_output_edit.setPlainText('{"character_name":"诺艾尔","speech":"你好"}\n')

    window._save_config()

    saved = yaml.safe_load(paths["characters"].read_text(encoding="utf-8"))
    assert saved[0]["name"] == DEFAULT_CHARACTER["name"]
    assert saved[0]["character_setting"] == DEFAULT_CHARACTER["character_setting"]
    message = window.template_validation_result_label.text()
    assert "发布前检查未通过" in message
    assert "角色名称不能为空" in message
    assert "第 1 行" in message
    assert "sprite" in message
    assert "修复建议：" in message
    assert "填写角色名称，例如：诺艾尔" in message
    assert "补齐对应 JSON 对象的必填字段，例如 sprite" in message
    assert "保存已取消" in window.save_status_label.text()
    assert COLOR_ERR in window.save_status_label.styleSheet()
    assert len(critical_calls) == 1
    assert "发布前检查未通过" in critical_calls[0]["text"]
    assert "修复建议：" in critical_calls[0]["text"]
    assert "填写角色名称，例如：诺艾尔" in critical_calls[0]["text"]
    assert "补齐对应 JSON 对象的必填字段，例如 sprite" in critical_calls[0]["text"]
    assert info_calls == []


def test_settings_window_save_allows_empty_optional_template_sample_output(
    settings_config, make_settings_window, monkeypatch
):
    paths = settings_config()
    info_calls = []
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))
    monkeypatch.setattr(QMessageBox, "critical", fake_message_recorder(critical_calls))
    window = make_settings_window()
    window.char_name_edit.setText("诺艾尔")
    window.char_setting_edit.setPlainText("认真可靠的见习骑士，负责陪伴玩家完成日常对话。")
    window.emotion_tags_edit.setPlainText("0: neutral")
    window.template_sample_output_edit.setPlainText("   \n")

    window._save_config()

    saved = yaml.safe_load(paths["characters"].read_text(encoding="utf-8"))
    assert saved[0]["name"] == "诺艾尔"
    assert saved[0]["character_setting"] == "认真可靠的见习骑士，负责陪伴玩家完成日常对话。"
    assert saved[0]["emotion_tags"] == "0: neutral"
    assert saved[0]["emotion_items"] == []
    assert "template_sample_output" not in saved[0]
    preflight_message = window.template_validation_result_label.text()
    assert "示例输出为空" in preflight_message
    assert "发布前检查未通过" not in preflight_message
    assert "配置已保存" in window.save_status_label.text()
    assert critical_calls == []
    assert len(info_calls) == 1


def test_settings_window_save_preserves_empty_legacy_emotion_tags_when_structured_items_exist(
    settings_config, make_settings_window, monkeypatch, tmp_path
):
    sprite_root = tmp_path / "sprites" / "诺艾尔"
    sprite_root.mkdir(parents=True)
    legacy_first = sprite_root / "legacy-first.png"
    legacy_second = sprite_root / "legacy-second.png"
    legacy_first.write_text("first", encoding="utf-8")
    legacy_second.write_text("second", encoding="utf-8")
    paths = settings_config(characters=[{
        "name": "诺艾尔",
        "color": "#87CEEB",
        "character_setting": "认真可靠的见习骑士，负责陪伴玩家完成日常对话。",
        "emotion_tags": "0: legacy-zero",
        "sprites": [{"path": str(legacy_first)}, {"path": str(legacy_second)}],
        "emotion_items": [{"id": 2, "label": "happy", "sprite_path": "structured-happy.png"}],
    }])
    info_calls = []
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))
    monkeypatch.setattr(QMessageBox, "critical", fake_message_recorder(critical_calls))
    window = make_settings_window()
    window.char_name_edit.setText("诺艾尔")
    window.char_setting_edit.setPlainText("认真可靠的见习骑士，负责陪伴玩家完成日常对话。")
    window.emotion_tags_edit.setPlainText("")
    window.template_sample_output_edit.setPlainText("   \n")

    window._save_config()

    saved = yaml.safe_load(paths["characters"].read_text(encoding="utf-8"))
    assert saved[0]["name"] == "诺艾尔"
    assert saved[0]["emotion_tags"] == "0: legacy-zero"
    assert saved[0]["emotion_items"] == [{"id": 2, "label": "happy", "sprite_path": "structured-happy.png"}]
    assert saved[0]["sprites"][0]["path"].endswith("legacy-first.png")
    assert saved[0]["sprites"][1]["path"].endswith("legacy-second.png")
    assert saved[0]["sprites"][0]["path"] != str(legacy_first)
    assert saved[0]["sprites"][1]["path"] != str(legacy_second)
    assert critical_calls == []
    assert len(info_calls) == 1


def test_settings_window_save_keeps_legacy_emotion_tags_when_no_structured_items_exist(
    settings_config, make_settings_window, monkeypatch
):
    paths = settings_config(characters=[{
        "name": "旧字段角色",
        "color": "#87CEEB",
        "character_setting": "旧字段回写保留测试。",
        "emotion_tags": "0: legacy-zero\n1: legacy-happy",
        "sprites": [],
        "emotion_items": [],
    }])
    info_calls = []
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))
    monkeypatch.setattr(QMessageBox, "critical", fake_message_recorder(critical_calls))
    window = make_settings_window()
    window.char_name_edit.setText("旧字段角色")
    window.char_setting_edit.setPlainText("旧字段回写保留测试。")
    window.emotion_tags_edit.setPlainText("0: legacy-zero\n1: legacy-happy")
    window.template_sample_output_edit.setPlainText("   \n")

    window._save_config()

    saved = yaml.safe_load(paths["characters"].read_text(encoding="utf-8"))
    assert saved[0]["emotion_tags"] == "0: legacy-zero\n1: legacy-happy"
    assert saved[0]["emotion_items"] == []
    assert critical_calls == []
    assert len(info_calls) == 1


def test_settings_window_save_does_not_overwrite_legacy_emotion_tags_from_structured_editor_text(
    settings_config, make_settings_window, monkeypatch
):
    paths = settings_config(characters=[{
        "name": "结构化角色",
        "color": "#87CEEB",
        "character_setting": "结构化保存应保持旧字段降级。",
        "emotion_tags": "0: legacy-zero\n1: legacy-happy",
        "sprites": [],
        "emotion_items": [{"id": 2, "label": "happy", "sprite_path": "structured-happy.png"}],
    }])
    info_calls = []
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))
    monkeypatch.setattr(QMessageBox, "critical", fake_message_recorder(critical_calls))
    window = make_settings_window()
    window.char_name_edit.setText("结构化角色")
    window.char_setting_edit.setPlainText("结构化保存应保持旧字段降级。")
    window.emotion_tags_edit.setPlainText("2: happy -> rewritten-from-editor.png")
    window.template_sample_output_edit.setPlainText("   \n")

    window._save_config()

    saved = yaml.safe_load(paths["characters"].read_text(encoding="utf-8"))
    assert saved[0]["emotion_tags"] == "0: legacy-zero\n1: legacy-happy"
    assert saved[0]["emotion_items"] == [{"id": 2, "label": "happy", "sprite_path": "structured-happy.png"}]
    assert critical_calls == []
    assert len(info_calls) == 1


def test_settings_window_save_keeps_legacy_emotion_tags_when_structured_items_use_legacy_zero_id(
    settings_config, make_settings_window, monkeypatch
):
    paths = settings_config(characters=[{
        "name": "零号兼容角色",
        "color": "#87CEEB",
        "character_setting": "零号结构化兼容测试。",
        "emotion_tags": "0: legacy-zero\n1: legacy-happy",
        "sprites": [],
        "emotion_items": [{"id": 0, "label": "legacy-zero", "sprite_path": "structured-zero.png"}],
    }])
    info_calls = []
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))
    monkeypatch.setattr(QMessageBox, "critical", fake_message_recorder(critical_calls))
    window = make_settings_window()
    window.char_name_edit.setText("零号兼容角色")
    window.char_setting_edit.setPlainText("零号结构化兼容测试。")
    window.emotion_tags_edit.setPlainText("0: legacy-zero -> editor-should-not-win.png")
    window.template_sample_output_edit.setPlainText("   \n")

    window._save_config()

    saved = yaml.safe_load(paths["characters"].read_text(encoding="utf-8"))
    assert saved[0]["emotion_tags"] == "0: legacy-zero\n1: legacy-happy"
    assert saved[0]["emotion_items"] == [{"id": 1, "label": "legacy-zero", "sprite_path": "structured-zero.png"}]
    assert critical_calls == []
    assert len(info_calls) == 1


def test_settings_window_save_allows_template_preflight_warnings_with_notice(
    settings_config, make_settings_window, monkeypatch
):
    paths = settings_config()
    info_calls = []
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))
    monkeypatch.setattr(QMessageBox, "critical", fake_message_recorder(critical_calls))
    window = make_settings_window()
    window.char_name_edit.setText("诺艾尔")
    window.char_setting_edit.setPlainText("可靠")
    window.emotion_tags_edit.setPlainText("   ")
    window.template_sample_output_edit.setPlainText(
        '{"character_name":"CG","speech":"","sprite":"夕阳下的教室"}\n'
    )

    window._save_config()

    saved = yaml.safe_load(paths["characters"].read_text(encoding="utf-8"))
    assert saved[0]["name"] == "诺艾尔"
    assert saved[0]["character_setting"] == "可靠"
    preflight_message = window.template_validation_result_label.text()
    assert "发布前检查可用，但有警告" in preflight_message
    assert "角色设定较短" in preflight_message
    assert "情绪标签为空" in preflight_message
    assert "CG 的 prompt 应放在 speech" in preflight_message
    status_message = window.save_status_label.text()
    assert "配置已保存" in status_message
    assert "有警告" in status_message
    assert "建议查看发布前检查" in status_message
    assert len(info_calls) == 1
    assert info_calls[0]["title"] == "配置已保存"
    assert info_calls[0]["text"] == status_message
    assert "有警告" in info_calls[0]["text"]
    assert "建议查看发布前检查" in info_calls[0]["text"]
    assert critical_calls == []


def test_settings_window_template_sample_uses_current_character_name(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()
    window.char_name_edit.setText("诺艾尔")

    window._fill_template_sample_output()

    sample = window.template_sample_output_edit.toPlainText()
    assert '"character_name": "诺艾尔"' in sample
    assert '"character_name": "小雪"' not in sample


def test_settings_window_template_sample_is_not_saved_to_character_config(settings_config, make_settings_window, monkeypatch):
    paths = settings_config()
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))
    window = make_settings_window()

    set_valid_template_preflight(window)
    window._fill_template_sample_output()
    window._save_config()

    saved = yaml.safe_load(paths["characters"].read_text(encoding="utf-8"))
    dumped = yaml.safe_dump(saved, allow_unicode=True)
    assert "template_sample_output" not in dumped
    assert len(info_calls) == 1


def test_settings_window_exposes_global_skill_library_list_for_default_selection(settings_config, make_settings_window):
    settings_config(system={
        "default_skills": ["shared"],
        "skills_root": "data/skills",
        "skill_presets": [{"name": "推理", "skills": ["mystery-a"]}],
    })
    window = make_settings_window()

    assert hasattr(window, "system_skill_list")
    assert window.system_skill_list is not None


def test_settings_window_exposes_skill_preset_crud_controls(settings_config, make_settings_window):
    settings_config(system={
        "default_skills": ["shared"],
        "skills_root": "data/skills",
        "skill_presets": [{"name": "推理", "skills": ["mystery-a"]}],
    })
    window = make_settings_window()

    assert hasattr(window, "skill_preset_list")
    assert hasattr(window, "add_skill_preset_button")
    assert hasattr(window, "rename_skill_preset_button")
    assert hasattr(window, "delete_skill_preset_button")


def test_settings_window_populates_skill_list_with_name_description_and_default_selection(settings_config, make_settings_window, monkeypatch):
    settings_config(system={
        "default_skills": ["shared"],
        "skills_root": "data/skills",
        "skill_presets": [{"name": "推理", "skills": ["mystery-a"]}],
    })

    import ui.settings_ui.window as settings_window_module

    class FakeSkillRepository:
        def __init__(self, roots):
            self.roots = roots

        def list_skills(self):
            return [
                type("Skill", (), {"name": "shared", "description": "Shared desc"})(),
                type("Skill", (), {"name": "mystery-a", "description": "Mystery desc"})(),
            ]

    monkeypatch.setattr(settings_window_module, "SkillRepository", FakeSkillRepository)
    window = make_settings_window()

    items = [window.system_skill_list.item(i).text() for i in range(window.system_skill_list.count())]
    assert items == ["shared — Shared desc", "mystery-a — Mystery desc"]
    assert window.system_skill_list.item(0).checkState().name == "Checked"
    assert window.system_skill_list.item(1).checkState().name == "Unchecked"


def test_settings_window_save_uses_checked_skill_list_as_global_defaults(settings_config, make_settings_window, monkeypatch):
    paths = settings_config(system={
        "default_skills": ["shared"],
        "skills_root": "data/skills",
        "skill_presets": [{"name": "推理", "skills": ["mystery-a"]}],
    })

    import ui.settings_ui.window as settings_window_module

    class FakeSkillRepository:
        def __init__(self, roots):
            self.roots = roots

        def list_skills(self):
            return [
                type("Skill", (), {"name": "shared", "description": "Shared desc"})(),
                type("Skill", (), {"name": "mystery-a", "description": "Mystery desc"})(),
            ]

    info_calls = []
    monkeypatch.setattr(settings_window_module, "SkillRepository", FakeSkillRepository)
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))
    window = make_settings_window()
    set_valid_template_preflight(window)

    window.system_skill_list.item(0).setCheckState(Qt.CheckState.Unchecked)
    window.system_skill_list.item(1).setCheckState(Qt.CheckState.Checked)
    window._save_config()

    saved_system = yaml.safe_load(paths["system"].read_text(encoding="utf-8"))
    assert saved_system["default_skills"] == ["mystery-a"]


def test_settings_window_populates_skill_preset_list_from_system_config(settings_config, make_settings_window, monkeypatch):
    settings_config(system={
        "default_skills": ["shared"],
        "skills_root": "data/skills",
        "skill_presets": [
            {"name": "推理", "skills": ["mystery-a"]},
            {"name": "日常", "skills": ["slice-of-life"]},
        ],
    })

    import ui.settings_ui.window as settings_window_module

    class FakeSkillRepository:
        def __init__(self, roots):
            self.roots = roots

        def list_skills(self):
            return []

    monkeypatch.setattr(settings_window_module, "SkillRepository", FakeSkillRepository)
    window = make_settings_window()

    items = [window.skill_preset_list.item(i).text() for i in range(window.skill_preset_list.count())]
    assert items == ["推理", "日常"]


def test_settings_window_add_skill_preset_updates_config_and_list(settings_config, make_settings_window, monkeypatch):
    settings_config(system={
        "default_skills": ["shared"],
        "skills_root": "data/skills",
        "skill_presets": [{"name": "推理", "skills": ["mystery-a"]}],
    })

    import ui.settings_ui.window as settings_window_module

    class FakeSkillRepository:
        def __init__(self, roots):
            self.roots = roots

        def list_skills(self):
            return []

    monkeypatch.setattr(settings_window_module, "SkillRepository", FakeSkillRepository)
    monkeypatch.setattr(settings_window_module.QInputDialog, "getText", lambda *args, **kwargs: ("日常", True))
    window = make_settings_window()

    window.add_skill_preset_button.click()

    assert [preset.name for preset in window.config.system_config.skill_presets] == ["推理", "日常"]
    items = [window.skill_preset_list.item(i).text() for i in range(window.skill_preset_list.count())]
    assert items == ["推理", "日常"]


def test_settings_window_rename_skill_preset_updates_config_and_list(settings_config, make_settings_window, monkeypatch):
    settings_config(system={
        "default_skills": ["shared"],
        "skills_root": "data/skills",
        "skill_presets": [{"name": "推理", "skills": ["mystery-a"]}],
    })

    import ui.settings_ui.window as settings_window_module

    class FakeSkillRepository:
        def __init__(self, roots):
            self.roots = roots

        def list_skills(self):
            return []

    monkeypatch.setattr(settings_window_module, "SkillRepository", FakeSkillRepository)
    monkeypatch.setattr(settings_window_module.QInputDialog, "getText", lambda *args, **kwargs: ("悬疑", True))
    window = make_settings_window()
    window.skill_preset_list.setCurrentRow(0)

    window.rename_skill_preset_button.click()

    assert [preset.name for preset in window.config.system_config.skill_presets] == ["悬疑"]
    assert [window.skill_preset_list.item(i).text() for i in range(window.skill_preset_list.count())] == ["悬疑"]


def test_settings_window_delete_skill_preset_updates_config_and_list(settings_config, make_settings_window, monkeypatch):
    settings_config(system={
        "default_skills": ["shared"],
        "skills_root": "data/skills",
        "skill_presets": [
            {"name": "推理", "skills": ["mystery-a"]},
            {"name": "日常", "skills": ["slice-of-life"]},
        ],
    })

    import ui.settings_ui.window as settings_window_module

    class FakeSkillRepository:
        def __init__(self, roots):
            self.roots = roots

        def list_skills(self):
            return []

    monkeypatch.setattr(settings_window_module, "SkillRepository", FakeSkillRepository)
    window = make_settings_window()
    window.skill_preset_list.setCurrentRow(0)

    window.delete_skill_preset_button.click()

    assert [preset.name for preset in window.config.system_config.skill_presets] == ["日常"]
    assert [window.skill_preset_list.item(i).text() for i in range(window.skill_preset_list.count())] == ["日常"]

def test_settings_window_template_sample_fill_button_inserts_valid_sample(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()
    window.char_name_edit.setText("诺艾尔")

    window.template_fill_sample_button.click()

    sample = window.template_sample_output_edit.toPlainText()
    sample_lines = [json.loads(line) for line in sample.splitlines() if line.strip()]
    by_character = {line["character_name"]: line for line in sample_lines}

    assert {"诺艾尔", "NARR", "CHOICE", "STAT", "CG"}.issubset(by_character)
    assert by_character["诺艾尔"]["speech"]
    assert by_character["诺艾尔"]["sprite"] == "0"
    assert "微风" in by_character["NARR"]["speech"]
    assert by_character["NARR"]["sprite"] == "-1"
    assert "/" in by_character["CHOICE"]["speech"]
    assert by_character["CHOICE"]["sprite"] == "-1"
    assert "好感度" in by_character["STAT"]["speech"]
    assert "+1" in by_character["STAT"]["speech"]
    assert by_character["STAT"]["sprite"] == "-1"
    assert "夕阳" in by_character["CG"]["speech"]
    assert "教室" in by_character["CG"]["speech"]
    assert "动漫风格" in by_character["CG"]["speech"]
    assert by_character["CG"]["sprite"] == "-1"
    assert by_character["CG"]["sprite"] != by_character["CG"]["speech"]
    assert "示例输出校验通过" in window.template_validation_result_label.text()


def test_settings_window_template_sample_type_combo_has_expected_options(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()

    options = [
        window.template_sample_type_combo.itemText(i)
        for i in range(window.template_sample_type_combo.count())
    ]
    assert options[:6] == ["完整示例", "基础对话", "情绪切换示例", "CG 示例", "剧情分支示例", "模板复用示例"]


def test_settings_window_template_library_review_sample_contains_narr_stat_choice_and_validates(
    settings_config, make_settings_window
):
    settings_config()
    window = make_settings_window()
    window.char_name_edit.setText("诺艾尔")
    window.template_sample_type_combo.setCurrentText("模板复用示例")

    window.template_fill_sample_button.click()

    sample_lines = _template_sample_lines(window)
    names = [line["character_name"] for line in sample_lines]
    assert names == ["NARR", "诺艾尔", "STAT", "CHOICE"]
    assert "模板库" in sample_lines[0]["speech"]
    assert "复核" in sample_lines[1]["speech"]
    assert "模板包" in sample_lines[2]["speech"]
    assert "/" in sample_lines[3]["speech"]
    assert "示例输出校验通过" in window.template_validation_result_label.text()


def test_settings_window_template_review_repair_sample_contains_warning_fix_flow_and_validates(
    settings_config, make_settings_window
):
    settings_config()
    window = make_settings_window()
    window.char_name_edit.setText("诺艾尔")
    window.template_sample_type_combo.setCurrentText("模板修正示例")

    window.template_fill_sample_button.click()

    sample_lines = _template_sample_lines(window)
    names = [line["character_name"] for line in sample_lines]
    assert names == ["NARR", "诺艾尔", "STAT", "CHOICE"]
    assert "警告" in sample_lines[0]["speech"] or "修复" in sample_lines[0]["speech"]
    assert "修正" in sample_lines[1]["speech"] or "补齐" in sample_lines[1]["speech"]
    assert "复查" in sample_lines[2]["speech"] or "重新检查" in sample_lines[2]["speech"]
    assert "/" in sample_lines[3]["speech"]
    assert "示例输出校验通过" in window.template_validation_result_label.text()


def test_settings_window_branching_story_sample_contains_stat_choice_without_cg_and_validates(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()
    window.char_name_edit.setText("诺艾尔")
    window.template_sample_type_combo.setCurrentText("剧情分支示例")

    window.template_fill_sample_button.click()

    sample_lines = _template_sample_lines(window)
    names = [line["character_name"] for line in sample_lines]
    by_character = {line["character_name"]: line for line in sample_lines}
    choices = [part.strip() for part in by_character["CHOICE"]["speech"].split("/")]

    assert names == ["NARR", "诺艾尔", "STAT", "CHOICE"]
    assert "CG" not in names
    assert by_character["NARR"]["speech"]
    assert by_character["NARR"]["sprite"] == "-1"
    assert by_character["诺艾尔"]["speech"]
    assert by_character["诺艾尔"]["sprite"] == "0"
    assert "好感度" in by_character["STAT"]["speech"]
    assert "线索" in by_character["STAT"]["speech"]
    assert by_character["STAT"]["sprite"] == "-1"
    assert 2 <= len(choices) <= 4
    assert all(choices)
    assert by_character["CHOICE"]["sprite"] == "-1"
    assert "示例输出校验通过" in window.template_validation_result_label.text()


def test_settings_window_emotion_switch_sample_uses_multiple_character_sprites_and_validates(
    settings_config, make_settings_window
):
    settings_config()
    window = make_settings_window()
    window.char_name_edit.setText("诺艾尔")
    window.template_sample_type_combo.setCurrentText("情绪切换示例")

    window.template_fill_sample_button.click()

    sample_lines = _template_sample_lines(window)
    names = [line["character_name"] for line in sample_lines]
    sprites = [line["sprite"] for line in sample_lines]

    assert names == ["诺艾尔", "诺艾尔", "诺艾尔", "NARR"]
    assert sprites == ["0", "1", "2", "-1"]
    assert all(line["speech"] for line in sample_lines)
    assert "笑" in sample_lines[1]["speech"] or "开心" in sample_lines[1]["speech"]
    assert "担心" in sample_lines[2]["speech"] or "认真" in sample_lines[2]["speech"]
    assert {"CG", "STAT", "CHOICE"}.isdisjoint(names)
    assert "示例输出校验通过" in window.template_validation_result_label.text()


def test_settings_window_basic_dialog_sample_excludes_stat_and_cg_and_validates(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()
    window.char_name_edit.setText("诺艾尔")
    window.template_sample_type_combo.setCurrentText("基础对话")

    window.template_fill_sample_button.click()

    names = _template_sample_character_names(window)
    assert names == ["诺艾尔", "NARR", "CHOICE"]
    assert "STAT" not in names
    assert "CG" not in names
    assert "示例输出校验通过" in window.template_validation_result_label.text()


def test_settings_window_cg_sample_contains_prompt_in_speech_and_validates(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()
    window.char_name_edit.setText("诺艾尔")
    window.template_sample_type_combo.setCurrentText("CG 示例")

    window.template_fill_sample_button.click()

    sample_lines = _template_sample_lines(window)
    by_character = {line["character_name"]: line for line in sample_lines}
    assert list(by_character) == ["诺艾尔", "CG", "CHOICE"]
    assert by_character["CG"]["speech"]
    assert "夕阳" in by_character["CG"]["speech"]
    assert "动漫风格" in by_character["CG"]["speech"]
    assert by_character["CG"]["sprite"] == "-1"
    assert by_character["CG"]["sprite"] != by_character["CG"]["speech"]
    assert "示例输出校验通过" in window.template_validation_result_label.text()


def test_settings_window_template_sample_type_is_not_saved_to_character_config(
    settings_config, make_settings_window, monkeypatch
):
    paths = settings_config()
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))
    window = make_settings_window()
    window.char_name_edit.setText("诺艾尔")
    window.char_setting_edit.setPlainText("认真可靠的见习骑士，负责陪伴玩家完成日常对话。")
    window.emotion_tags_edit.setPlainText("0: neutral")
    window.template_sample_type_combo.setCurrentText("基础对话")
    window.template_fill_sample_button.click()

    window._save_config()

    saved = yaml.safe_load(paths["characters"].read_text(encoding="utf-8"))
    dumped = yaml.safe_dump(saved, allow_unicode=True)
    assert "template_sample_type" not in dumped
    assert "template_sample_type_combo" not in dumped
    assert "完整示例" not in dumped
    assert "基础对话" not in dumped
    assert "情绪切换示例" not in dumped
    assert "CG 示例" not in dumped
    assert "剧情分支示例" not in dumped


def test_settings_window_template_copy_result_button_exists_and_clicks(settings_config, make_settings_window, monkeypatch):
    settings_config()
    window = make_settings_window()
    copied = []
    monkeypatch.setattr(window, "_set_clipboard_text", copied.append)

    assert window.template_copy_validation_result_button.text() == "复制结果"
    window.template_validation_result_label.setText("示例输出校验通过。")
    window.template_copy_validation_result_button.click()

    assert copied == ["示例输出校验通过。"]


def test_settings_window_template_copy_validation_result_copies_errors_without_losing_label(settings_config, make_settings_window, monkeypatch):
    settings_config()
    window = make_settings_window()
    copied = []
    monkeypatch.setattr(window, "_set_clipboard_text", copied.append)

    window.template_sample_output_edit.setPlainText('{"character_name":"小雪","speech":"你好"}\n')
    window._validate_template_sample_output()
    original_message = window.template_validation_result_label.text()

    window.template_copy_validation_result_button.click()

    assert copied == [original_message]
    assert "示例输出有错误" in copied[0]
    assert "sprite" in copied[0]
    assert window.template_validation_result_label.text() == original_message


def test_settings_window_template_copy_validation_result_requires_existing_result(settings_config, make_settings_window, monkeypatch):
    settings_config()
    window = make_settings_window()
    copied = []
    monkeypatch.setattr(window, "_set_clipboard_text", copied.append)

    window.template_validation_result_label.setText("   ")
    window.template_copy_validation_result_button.click()

    assert copied == []
    assert window.template_validation_result_label.text() == "暂无可复制的校验结果。"
    assert window.template_validation_result_label.toolTip() == "暂无可复制的校验结果。"
    assert COLOR_ERR in window.template_validation_result_label.styleSheet()


def test_settings_window_tts_provider_options_match_runtime_factory(settings_config, make_settings_window):
    settings_config(api={"tts_provider": "none"})
    window = make_settings_window()
    options = [window.tts_provider_combo.itemText(i) for i in range(window.tts_provider_combo.count())]
    assert options == ["none", *sorted(TTSAdapterFactory._registry)]


def test_settings_window_loads_and_saves_t2i_settings(settings_config, make_settings_window, monkeypatch):
    paths = settings_config(api={
        "t2i_provider": "comfyui",
        "t2i_api_url": "http://127.0.0.1:8188",
        "t2i_checkpoint": "animagineXLV31_v31.safetensors",
    })
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))

    window = make_settings_window()
    assert window.t2i_provider_combo.currentText() == "comfyui"
    assert window.t2i_api_url_edit.text() == "http://127.0.0.1:8188"
    assert window.t2i_checkpoint_edit.text() == "animagineXLV31_v31.safetensors"
    assert "ComfyUI" in window.t2i_hint_label.text()
    assert "Checkpoint" in window.t2i_hint_label.text()
    assert "已安装模型名称" in window.t2i_hint_label.text()
    assert "ckpt_name" in window.t2i_hint_label.text()
    assert "重启聊天窗口后生效" in window.t2i_hint_label.text()

    window.t2i_provider_combo.setCurrentText("none")
    window.t2i_api_url_edit.setText("http://localhost:8189")
    window.t2i_checkpoint_edit.setText("  noobaiXLNAIXL_epsilonPred11Version.safetensors  ")
    set_valid_template_preflight(window)
    window._save_config()

    saved = yaml.safe_load(paths["api_local"].read_text(encoding="utf-8"))
    assert saved["t2i_provider"] == "none"
    assert saved["t2i_api_url"] == "http://localhost:8189"
    assert saved["t2i_checkpoint"] == "noobaiXLNAIXL_epsilonPred11Version.safetensors"
    assert len(info_calls) == 1
    assert "配置已保存" in info_calls[0]["text"]


def test_settings_window_checks_llm_config_ready(settings_config, make_settings_window):
    settings_config(api={
        "llm_provider": "deepseek",
        "llm_api_key": {"deepseek": "sk-test"},
        "llm_base_url": "https://api.deepseek.com/v1",
        "llm_model": {"deepseek": "deepseek-chat"},
    })

    window = make_settings_window()
    assert window.llm_check_button.text() == "检查 LLM 配置"

    window.llm_check_button.click()

    message = window.save_status_label.text()
    assert "LLM 配置看起来可用" in message
    assert "deepseek" in message
    assert "deepseek-chat" in message
    assert "sk-test" not in message
    assert COLOR_OK in window.save_status_label.styleSheet()


def test_settings_window_reports_missing_llm_config(settings_config, make_settings_window):
    settings_config(api={
        "llm_provider": "deepseek",
        "llm_api_key": {"deepseek": ""},
        "llm_base_url": "",
        "llm_model": {"deepseek": ""},
    })

    window = make_settings_window()
    window._check_llm_config()

    assert "LLM 配置不完整" in window.save_status_label.text()
    assert "API Key" in window.save_status_label.text()
    assert "Base URL" in window.save_status_label.text()
    assert "模型 ID" in window.save_status_label.text()
    assert COLOR_ERR in window.save_status_label.styleSheet()


def test_settings_window_checks_current_llm_widget_values_without_leaking_api_key(settings_config, make_settings_window):
    settings_config(api={
        "llm_provider": "openai",
        "llm_api_key": {"openai": "sk-loaded"},
        "llm_base_url": "https://api.openai.com/v1",
        "llm_model": {"openai": "gpt-4o-mini"},
    })

    window = make_settings_window()
    window.api_key_edit.setText(" sk-edited ")
    window.base_url_edit.setText(" https://edited.example/v1 ")
    window.model_edit.setText(" model-edited ")
    window._check_llm_config()

    assert "openai" in window.save_status_label.text()
    assert "model-edited" in window.save_status_label.text()
    assert "sk-edited" not in window.save_status_label.text()


def test_settings_window_save_rechecks_llm_config_ready_without_leaking_api_key(
    settings_config, make_settings_window, monkeypatch
):
    settings_config(api={
        "llm_provider": "deepseek",
        "llm_api_key": {"deepseek": "old-key"},
        "llm_base_url": "https://old.example/v1",
        "llm_model": {"deepseek": "old-model"},
    })
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))

    window = make_settings_window()
    window.api_key_edit.setText(" sk-new-secret ")
    window.base_url_edit.setText(" https://api.deepseek.com/v1 ")
    window.model_edit.setText(" deepseek-chat ")
    set_valid_template_preflight(window)

    window._save_config()

    message = window.save_status_label.text()
    assert "配置已保存" in message
    assert "LLM 配置看起来可用" in message
    assert "deepseek" in message
    assert "deepseek-chat" in message
    assert "sk-new-secret" not in message
    assert COLOR_OK in window.save_status_label.styleSheet()
    assert info_calls == [{"title": "配置已保存", "text": message}]


def test_settings_window_save_rechecks_llm_config_missing_fields(
    settings_config, make_settings_window, monkeypatch
):
    settings_config(api={
        "llm_provider": "deepseek",
        "llm_api_key": {"deepseek": "old-key"},
        "llm_base_url": "https://old.example/v1",
        "llm_model": {"deepseek": "old-model"},
    })
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))

    window = make_settings_window()
    window.api_key_edit.setText(" ")
    window.base_url_edit.setText(" ")
    window.model_edit.setText(" ")
    set_valid_template_preflight(window)

    window._save_config()

    message = window.save_status_label.text()
    assert "配置已保存" in message
    assert "LLM 配置不完整" in message
    assert "API Key" in message
    assert "Base URL" in message
    assert "模型 ID" in message
    assert COLOR_ERR in window.save_status_label.styleSheet()
    assert info_calls == [{"title": "配置已保存", "text": message}]


class FakeHttpResponse:
    def __init__(self, body=b"{}"):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


def test_settings_window_checks_comfyui_connection_success(settings_config, make_settings_window, monkeypatch):
    settings_config(api={
        "t2i_provider": "comfyui",
        "t2i_api_url": "http://127.0.0.1:8188/",
    })
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append({"url": req.full_url, "method": req.get_method(), "timeout": timeout})
        return FakeHttpResponse(b'{"system": {}}')

    monkeypatch.setattr("ui.settings_ui.api_controller.request.urlopen", fake_urlopen)

    window = make_settings_window()
    window._check_comfyui_connection()

    assert calls == [{
        "url": "http://127.0.0.1:8188/system_stats",
        "method": "GET",
        "timeout": 2.0,
    }]
    assert "ComfyUI 连接成功" in window.save_status_label.text()
    assert COLOR_OK in window.save_status_label.styleSheet()


def test_settings_window_reports_comfyui_connection_failure(settings_config, make_settings_window, monkeypatch):
    settings_config(api={
        "t2i_provider": "comfyui",
        "t2i_api_url": "http://127.0.0.1:8188",
    })

    def fake_urlopen(req, timeout=None):
        raise URLError("refused")

    monkeypatch.setattr("ui.settings_ui.api_controller.request.urlopen", fake_urlopen)

    window = make_settings_window()
    window._check_comfyui_connection()

    assert "ComfyUI 连接失败" in window.save_status_label.text()
    assert "refused" in window.save_status_label.text()
    assert COLOR_ERR in window.save_status_label.styleSheet()


def test_settings_window_reports_empty_comfyui_url_without_request(settings_config, make_settings_window, monkeypatch):
    settings_config(api={
        "t2i_provider": "comfyui",
        "t2i_api_url": "",
    })

    def fail_urlopen(req, timeout=None):
        raise AssertionError("urlopen should not be called for empty ComfyUI URL")

    monkeypatch.setattr("ui.settings_ui.api_controller.request.urlopen", fail_urlopen)

    window = make_settings_window()
    window._check_comfyui_connection()

    assert "ComfyUI API URL 不能为空" in window.save_status_label.text()
    assert COLOR_ERR in window.save_status_label.styleSheet()


def test_settings_window_skips_comfyui_check_when_t2i_disabled(settings_config, make_settings_window, monkeypatch):
    settings_config(api={
        "t2i_provider": "none",
        "t2i_api_url": "http://127.0.0.1:8188",
    })

    def fail_urlopen(req, timeout=None):
        raise AssertionError("urlopen should not be called when T2I is disabled")

    monkeypatch.setattr("ui.settings_ui.api_controller.request.urlopen", fail_urlopen)

    window = make_settings_window()
    window._check_comfyui_connection()

    assert "请先将 T2I / CG 引擎切换为 comfyui" in window.save_status_label.text()
    assert COLOR_ERR in window.save_status_label.styleSheet()


def test_settings_window_loads_and_saves_tts_speed(settings_config, make_settings_window, monkeypatch):
    paths = settings_config(api={
        "tts_provider": "edge-tts",
        "gpt_sovits_url": "http://tts.local",
        "tts_speed": 1.25,
    }, characters=[])
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))

    window = make_settings_window()
    assert window.tts_provider_combo.currentText() == "edge-tts"
    assert window.tts_url_edit.text() == "http://tts.local"
    assert window.tts_speed_spin.value() == pytest.approx(1.25)

    window.tts_speed_spin.setValue(0.85)
    set_valid_template_preflight(window)
    window._save_config()

    saved = yaml.safe_load(paths["api_local"].read_text(encoding="utf-8"))
    assert saved["tts_speed"] == pytest.approx(0.85)
    assert len(info_calls) == 1
    assert "配置已保存" in info_calls[0]["text"]
    assert "LLM 配置不完整" in info_calls[0]["text"]


def test_settings_window_loads_and_saves_tts_voice(settings_config, make_settings_window, monkeypatch):
    paths = settings_config(api={"tts_provider": "edge-tts", "tts_voice": "ja-JP-NanamiNeural"})
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))

    window = make_settings_window()
    assert window.tts_voice_edit.text() == "ja-JP-NanamiNeural"

    window.tts_voice_edit.setText("zh-CN-XiaoxiaoNeural")
    set_valid_template_preflight(window)
    window._save_config()

    saved = yaml.safe_load(paths["api_local"].read_text(encoding="utf-8"))
    assert saved["tts_voice"] == "zh-CN-XiaoxiaoNeural"
    assert "配置已保存" in info_calls[0]["text"]


def test_settings_window_shows_edge_tts_hint_without_service_url(settings_config, make_settings_window):
    settings_config(api={
        "tts_provider": "edge-tts",
        "gpt_sovits_url": "http://should-not-matter",
        "tts_speed": 1.0,
    })

    window = make_settings_window()
    assert window.tts_provider_combo.currentText() == "edge-tts"
    assert "edge-tts" in window.tts_hint_label.text()
    assert "不需要填写服务 URL" in window.tts_hint_label.text()
    assert "重启聊天窗口后生效" in window.tts_hint_label.text()

    window.tts_provider_combo.setCurrentText("gpt-sovits")

    assert "gpt-sovits" in window.tts_hint_label.text()
    assert "需要填写 TTS 服务 URL" in window.tts_hint_label.text()
    assert "重启聊天窗口后生效" in window.tts_hint_label.text()


def test_settings_window_shows_disabled_tts_hint(settings_config, make_settings_window):
    settings_config(api={
        "tts_provider": "none",
    })

    window = make_settings_window()
    assert "已关闭" in window.tts_hint_label.text()
    assert "不会合成语音" in window.tts_hint_label.text()


def test_settings_window_saves_character_display_name(settings_config, make_settings_window, monkeypatch):
    paths = settings_config()
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder(info_calls))

    window = make_settings_window()
    assert window.char_name_edit.text() == "小雪"
    assert "配置已加载" in window.save_status_label.text()
    assert window.save_status_label.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Ignored
    assert window.save_status_label.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Preferred

    set_valid_template_preflight(window, character_name="诺艾尔")
    window._save_config()

    saved = yaml.safe_load(paths["characters"].read_text(encoding="utf-8"))
    assert saved[0]["name"] == "诺艾尔"
    assert len(info_calls) == 1
    assert info_calls[0]["title"] == "配置已保存"
    assert "配置已保存" in info_calls[0]["text"]
    assert "LLM 配置不完整" in info_calls[0]["text"]
    assert "配置已保存" in window.save_status_label.text()
    assert "LLM 配置不完整" in window.save_status_label.text()


def test_settings_window_reports_save_failure(settings_config, make_settings_window, monkeypatch):
    settings_config()
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", fake_message_recorder(critical_calls))

    window = make_settings_window()

    def raise_save_error():
        raise RuntimeError("boom")

    monkeypatch.setattr(window.config, "save_api_config", raise_save_error)
    set_valid_template_preflight(window)

    window._save_config()

    assert len(critical_calls) == 1
    assert critical_calls[0]["title"] == "错误"
    assert "保存失败" in critical_calls[0]["text"]
    assert "boom" in critical_calls[0]["text"]
    assert "保存失败" in window.save_status_label.text()
    assert "boom" in window.save_status_label.text()
    assert COLOR_ERR in window.save_status_label.styleSheet()
    assert window.save_status_label.toolTip() == window.save_status_label.text()


def test_settings_window_switching_character_refreshes_sprite_list(settings_config, make_settings_window):
    settings_config(
        characters=[
            {
                "name": "小雪",
                "character_setting": "第一个角色设定",
                "emotion_tags": "0: neutral",
                "sprites": [{"path": "old-default.png"}],
            },
            {
                "name": "新角色",
                "character_setting": "第二个角色设定",
                "emotion_tags": "1: happy",
                "sprites": [{"path": "new-default.png"}, {"path": "new-happy.png"}],
            },
        ]
    )
    window = make_settings_window()

    assert window.sprite_list.count() == 1
    assert window.sprite_list.item(0).text() == "立绘 #01"

    window.character_list.setCurrentRow(1)

    assert window.sprite_list.count() == 2
    assert window.sprite_list.item(0).text() == "立绘 #01"
    assert window.sprite_list.item(1).text() == "立绘 #02"


def test_settings_window_prefers_structured_emotion_items_in_detail_editor(settings_config, make_settings_window):
    settings_config(
        characters=[
            {
                "name": "结构化角色",
                "character_setting": "结构化详情区测试",
                "emotion_tags": "legacy: should not lead",
                "emotion_items": [
                    {"id": 1, "label": "neutral", "sprite_path": "neutral.png"},
                    {"id": 2, "label": "happy", "sprite_path": "happy.png"},
                ],
                "sprites": [{"path": "legacy-first.png"}, {"path": "legacy-second.png"}],
            }
        ]
    )
    window = make_settings_window()

    assert window.emotion_tags_edit.toPlainText() == "1: neutral\n2: happy"


def test_settings_window_loads_structured_emotion_items_into_binding_table(settings_config, make_settings_window):
    settings_config(characters=[{
        "name": "结构化角色",
        "character_setting": "结构化情绪表格测试",
        "emotion_tags": "legacy: should not lead",
        "emotion_items": [
            {"id": 1, "label": "neutral", "sprite_path": "neutral.png"},
            {"id": 2, "label": "happy", "sprite_path": "happy.png"},
        ],
        "sprites": [{"path": "neutral.png"}, {"path": "happy.png"}],
    }])
    window = make_settings_window()

    table = window.emotion_binding_table
    assert table.columnCount() == 4
    assert [table.horizontalHeaderItem(i).text() for i in range(4)] == ["情绪ID", "显示名称", "绑定立绘", "操作"]
    assert table.rowCount() == 2
    assert table.item(0, 0).text() == "1"
    assert table.item(0, 1).text() == "neutral"
    assert table.cellWidget(0, 2).currentText() == "立绘 #01"
    assert table.cellWidget(0, 2).currentData() == "neutral.png"
    assert table.cellWidget(0, 3).text() == "导入图片"
    assert table.item(1, 0).text() == "2"
    assert table.item(1, 1).text() == "happy"
    assert table.cellWidget(1, 2).currentText() == "立绘 #02"
    assert table.cellWidget(1, 2).currentData() == "happy.png"
    assert table.cellWidget(1, 3).text() == "导入图片"


def test_settings_window_adds_and_deletes_emotion_binding_rows(settings_config, make_settings_window):
    settings_config(characters=[{
        "name": "绑定编辑角色",
        "character_setting": "绑定编辑测试",
        "emotion_tags": "",
        "emotion_items": [{"id": 1, "label": "neutral", "sprite_path": "neutral.png"}],
        "sprites": [{"path": "neutral.png"}, {"path": "happy.png"}],
    }])
    window = make_settings_window()
    table = window.emotion_binding_table

    window.add_emotion_binding_button.click()

    assert table.rowCount() == 2
    assert table.item(1, 0).text() == "2"
    assert table.item(1, 1).text() == "new_emotion"
    assert table.cellWidget(1, 2).currentText() == "立绘 #01"

    table.selectRow(1)
    window.delete_emotion_binding_button.click()

    assert table.rowCount() == 1
    assert table.item(0, 1).text() == "neutral"


def test_settings_window_save_writes_emotion_bindings_from_table(settings_config, make_settings_window, monkeypatch):
    paths = settings_config(characters=[{
        "name": "保存绑定角色",
        "character_setting": "保存绑定测试。",
        "emotion_tags": "0: legacy-neutral",
        "emotion_items": [],
        "sprites": [{"path": "neutral.png"}, {"path": "happy.png"}],
    }])
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder([]))
    monkeypatch.setattr(QMessageBox, "critical", fake_message_recorder([]))
    window = make_settings_window()
    window.char_name_edit.setText("保存绑定角色")
    window.char_setting_edit.setPlainText("保存绑定测试。")
    window.template_sample_output_edit.setPlainText("   \n")

    table = window.emotion_binding_table
    window.add_emotion_binding_button.click()
    table.item(0, 0).setText("1")
    table.item(0, 1).setText("neutral")
    table.cellWidget(0, 2).setCurrentText("neutral.png")
    window.add_emotion_binding_button.click()
    table.item(1, 0).setText("2")
    table.item(1, 1).setText("happy")
    table.cellWidget(1, 2).setCurrentIndex(table.cellWidget(1, 2).findData("happy.png"))

    window._save_config()

    saved = yaml.safe_load(paths["characters"].read_text(encoding="utf-8"))
    assert saved[0]["emotion_items"] == [
        {"id": 1, "label": "neutral", "sprite_path": "neutral.png"},
        {"id": 2, "label": "happy", "sprite_path": "happy.png"},
    ]


def test_settings_window_per_emotion_import_adds_sprite_and_binds_row(
    settings_config, make_settings_window, monkeypatch, tmp_path
):
    imported = tmp_path / "surprised.png"
    imported.write_text("sprite", encoding="utf-8")
    settings_config(characters=[{
        "name": "逐行情绪角色",
        "character_setting": "逐行导入测试。",
        "emotion_tags": "",
        "emotion_items": [{"id": 1, "label": "surprised", "sprite_path": ""}],
        "sprites": [{"path": "neutral.png"}],
    }])
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(imported), "图片文件 (*.png)"),
    )
    window = make_settings_window()
    table = window.emotion_binding_table

    table.cellWidget(0, 3).click()

    assert table.cellWidget(0, 2).currentText() == "立绘 #02"
    assert table.cellWidget(0, 2).currentData() == str(imported)
    assert any(table.cellWidget(0, 2).itemData(i) == "neutral.png" for i in range(table.cellWidget(0, 2).count()))
    assert window.sprite_list.item(window.sprite_list.count() - 1).text() == "立绘 #02"


def test_settings_window_fill_default_emotions_preserves_existing_bindings(settings_config, make_settings_window):
    settings_config(characters=[{
        "name": "默认补齐角色",
        "character_setting": "默认情绪补齐测试。",
        "emotion_tags": "",
        "emotion_items": [
            {"id": 1, "label": "neutral", "sprite_path": "neutral.png"},
            {"id": 2, "label": "happy", "sprite_path": "happy.png"},
        ],
        "sprites": [{"path": "neutral.png"}, {"path": "happy.png"}],
    }])
    window = make_settings_window()
    table = window.emotion_binding_table

    window.fill_default_emotions_button.click()

    rows = [
        (table.item(row, 0).text(), table.item(row, 1).text(), table.cellWidget(row, 2).currentText())
        for row in range(table.rowCount())
    ]
    assert rows == [
        ("1", "neutral", "立绘 #01"),
        ("2", "happy", "立绘 #02"),
        ("3", "sad", "未绑定"),
        ("4", "angry", "未绑定"),
        ("5", "surprised", "未绑定"),
    ]


def test_settings_window_character_card_renders_explicit_avatar_image(
    settings_config, make_settings_window, tmp_path
):
    avatar_path = tmp_path / "explicit-avatar.png"
    image = QImage(12, 8, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.red)
    assert image.save(str(avatar_path))
    settings_config(
        characters=[
            {
                "name": "头像角色",
                "avatar": str(avatar_path),
                "character_setting": "头像渲染测试",
                "emotion_items": [],
                "sprites": [],
            }
        ]
    )

    window = make_settings_window()
    avatar_label = window.character_card_avatar_labels[0]

    assert avatar_label.pixmap() is not None
    assert avatar_label.pixmap().isNull() is False
    assert avatar_label.text() == ""
    assert avatar_label.toolTip() == str(avatar_path)


def test_settings_window_avatar_editor_imports_previews_and_clears_pending_avatar(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    imported = tmp_path / "new-avatar.png"
    image = QImage(16, 12, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.blue)
    assert image.save(str(imported))
    settings_config(characters=[{**DEFAULT_CHARACTER, "sprites": [{"path": "fallback.png"}]}])
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(imported), ""))
    window = make_settings_window()

    window.import_avatar_button.click()

    assert window.avatar_path_edit.text() == str(imported)
    assert window.avatar_preview_label.pixmap() is not None
    assert window.avatar_preview_label.pixmap().isNull() is False
    assert "显式头像" in window.avatar_status_label.text()
    assert window.config.characters[0].avatar == ""

    window.clear_avatar_button.click()

    assert window.avatar_path_edit.text() == ""
    assert "第一张立绘" in window.avatar_status_label.text()


def test_settings_window_save_archives_avatar_and_refreshes_character_card(
    settings_config, make_settings_window, tmp_path, monkeypatch
):
    imported = tmp_path / "avatar-source.png"
    image = QImage(12, 12, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.red)
    assert image.save(str(imported))
    paths = settings_config()
    monkeypatch.setattr(QMessageBox, "information", fake_message_recorder([]))
    monkeypatch.setattr(QMessageBox, "critical", fake_message_recorder([]))
    window = make_settings_window()
    window.avatar_path_edit.setText(str(imported))

    window._save_config()

    expected = paths["characters"].parent.parent / "avatars" / "小雪" / imported.name
    assert expected.read_bytes() == imported.read_bytes()
    assert window.config.characters[0].avatar == str(expected.resolve())
    assert window.character_card_avatar_labels[0].toolTip() == str(expected.resolve())


def test_settings_window_character_card_avatar_prefers_explicit_avatar_over_first_sprite(settings_config, make_settings_window):
    settings_config(
        characters=[
            {
                "name": "头像角色",
                "avatar": "explicit-avatar.png",
                "character_setting": "头像边界测试",
                "emotion_tags": "legacy: avatar boundary",
                "emotion_items": [
                    {"id": 1, "label": "neutral", "sprite_path": "structured-default.png"},
                ],
                "sprites": [{"path": "legacy-first.png"}, {"path": "legacy-second.png"}],
            }
        ]
    )
    window = make_settings_window()

    avatar_label = window.character_card_avatar_labels[0]
    assert avatar_label.text() == "头像"
    assert avatar_label.toolTip() == "explicit-avatar.png"


def test_settings_window_character_card_avatar_uses_placeholder_when_no_avatar_or_sprites_exist(settings_config, make_settings_window):
    settings_config(
        characters=[
            {
                "name": "占位头像角色",
                "character_setting": "无头像无立绘时应显示占位头像。",
                "emotion_tags": "0: neutral",
                "emotion_items": [],
                "sprites": [],
            }
        ]
    )
    window = make_settings_window()

    assert window.character_card_avatar_labels[0].text() == "头像"


def test_settings_window_character_card_avatar_uses_structured_primary_sprite_when_no_explicit_avatar_exists(settings_config, make_settings_window):
    settings_config(
        characters=[
            {
                "name": "结构化头像角色",
                "character_setting": "无显式头像时应回退到结构化默认图。",
                "emotion_tags": "0: legacy-neutral",
                "emotion_items": [{"id": 1, "label": "neutral", "sprite_path": "structured-default.png"}],
                "sprites": [{"path": "legacy-first.png"}, {"path": "legacy-second.png"}],
            }
        ]
    )
    window = make_settings_window()

    avatar_label = window.character_card_avatar_labels[0]
    assert avatar_label.text() == "头像"
    assert avatar_label.toolTip() == "structured-default.png"


def test_settings_window_character_card_avatar_falls_back_to_first_legacy_sprite_when_no_structured_default_exists(settings_config, make_settings_window):
    settings_config(
        characters=[
            {
                "name": "legacy回退角色",
                "character_setting": "无结构化默认图时应回退到第一张 legacy 立绘。",
                "emotion_tags": "0: legacy-neutral",
                "emotion_items": [{"id": 1, "label": "neutral", "sprite_path": ""}],
                "sprites": [{"path": "legacy-first.png"}, {"path": "legacy-second.png"}],
            }
        ]
    )
    window = make_settings_window()

    avatar_label = window.character_card_avatar_labels[0]
    assert avatar_label.text() == "头像"
    assert avatar_label.toolTip() == "legacy-first.png"


def test_settings_window_does_not_surface_legacy_emotion_tags_as_primary_detail_text_when_structured_items_exist(settings_config, make_settings_window):
    settings_config(
        characters=[
            {
                "name": "旧字段降级角色",
                "character_setting": "旧字段降级测试",
                "emotion_tags": "0: legacy-neutral\n1: legacy-happy",
                "emotion_items": [
                    {"id": 1, "label": "neutral", "sprite_path": "neutral.png"},
                    {"id": 2, "label": "happy", "sprite_path": "happy.png"},
                ],
                "sprites": [{"path": "legacy-first.png"}, {"path": "legacy-second.png"}],
            }
        ]
    )
    window = make_settings_window()

    detail_text = window.emotion_tags_edit.toPlainText()
    assert detail_text == "1: neutral\n2: happy"
    assert "legacy-neutral" not in detail_text
    assert "legacy-happy" not in detail_text


def test_settings_window_switching_away_and_back_restores_structured_detail_text(settings_config, make_settings_window):
    settings_config(
        characters=[
            {
                "name": "结构化角色",
                "character_setting": "切换恢复测试。",
                "emotion_tags": "0: legacy-neutral\n1: legacy-happy",
                "emotion_items": [
                    {"id": 1, "label": "neutral", "sprite_path": "neutral.png"},
                    {"id": 2, "label": "happy", "sprite_path": "happy.png"},
                ],
                "sprites": [{"path": "legacy-first.png"}],
            },
            {
                "name": "第二角色",
                "character_setting": "第二角色设定。",
                "emotion_tags": "0: side-neutral",
                "emotion_items": [],
                "sprites": [{"path": "side-default.png"}],
            },
        ]
    )
    window = make_settings_window()

    assert window.emotion_tags_edit.toPlainText() == "1: neutral\n2: happy"

    window.emotion_tags_edit.setPlainText("0: edited-legacy-text")
    window.character_list.setCurrentRow(1)
    assert window.emotion_tags_edit.toPlainText() == "0: side-neutral"

    window.character_list.setCurrentRow(0)
    assert window.emotion_tags_edit.toPlainText() == "1: neutral\n2: happy"
    assert "edited-legacy-text" not in window.emotion_tags_edit.toPlainText()


def test_settings_window_exposes_core_automation_anchors(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()

    def assert_anchor(widget, object_name: str, accessible_name: str):
        assert widget.objectName() == object_name
        assert widget.accessibleName() == accessible_name

    assert window.objectName() == "settings_window"
    assert_anchor(window.settings_tabs, "settings_tabs", "Settings tabs")
    assert_anchor(window.save_status_label, "save_status_label", "Save status")
    assert_anchor(window.save_settings_button, "save_settings_button", "Save settings")
    assert_anchor(window.llm_provider_combo, "llm_provider_combo", "LLM provider")
    assert_anchor(window.api_key_edit, "api_key_input", "API key")
    assert_anchor(window.base_url_edit, "base_url_input", "Base URL")
    assert_anchor(window.model_edit, "model_input", "Model ID")
    assert_anchor(window.llm_check_button, "llm_check_button", "Check LLM configuration")
    assert_anchor(window.temp_spin, "temperature_spin", "LLM temperature")
    assert_anchor(window.t2i_provider_combo, "t2i_provider_combo", "T2I provider")
    assert_anchor(window.t2i_api_url_edit, "t2i_api_url_input", "ComfyUI API URL")
    assert_anchor(window.t2i_checkpoint_edit, "t2i_checkpoint_input", "ComfyUI checkpoint")
    assert_anchor(window.t2i_check_button, "t2i_check_button", "Test ComfyUI connection")
    assert_anchor(window.scene_list, "scene_list", "Scene background list")
    assert_anchor(window.add_scene_button, "add_scene_button", "Add scene image")
    assert_anchor(window.remove_scene_button, "remove_scene_button", "Remove selected scene")
    assert_anchor(window.background_path_combo, "background_path_combo", "Current background")
    assert not hasattr(window, "bgm_list")
    assert_anchor(window.tts_provider_combo, "tts_provider_combo", "TTS provider")
    assert_anchor(window.tts_url_edit, "tts_url_input", "TTS service URL")
    assert_anchor(window.tts_voice_edit, "tts_voice_input", "TTS voice")
    assert_anchor(window.tts_speed_spin, "tts_speed_spin", "TTS speed")
    assert_anchor(window.lang_combo, "language_combo", "Interface language")
    assert_anchor(window.voice_lang_combo, "voice_language_combo", "Voice language")
    assert_anchor(window.system_default_skills_edit, "system_default_skills_input", "Global default skills")


def test_character_tab_exposes_automation_anchors(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()

    def assert_anchor(widget, object_name: str, accessible_name: str):
        assert widget.objectName() == object_name
        assert widget.accessibleName() == accessible_name

    assert_anchor(window.character_list, "character_list", "Character list")
    assert_anchor(window.add_character_button, "add_character_button", "Add character")
    assert_anchor(window.char_name_edit, "character_name_input", "Character name")
    assert_anchor(window.char_default_skills_edit, "character_default_skills_input", "Character default skills")
    assert_anchor(window.char_setting_edit, "character_setting_input", "Character setting")
    assert_anchor(window.emotion_tags_edit, "emotion_tags_input", "Emotion tags")
    assert_anchor(window.emotion_binding_table, "emotion_binding_table", "Emotion sprite binding table")
    assert_anchor(window.add_emotion_binding_button, "add_emotion_button", "Add emotion binding")
    assert_anchor(window.fill_default_emotions_button, "fill_default_emotions_button", "Fill default emotions")
    assert_anchor(window.delete_emotion_binding_button, "remove_emotion_button", "Remove selected emotion binding")
    assert_anchor(window.sprite_list, "sprite_list", "Sprite list")
    assert_anchor(window.import_sprites_button, "import_sprite_button", "Import sprites")
    assert_anchor(window.template_sample_output_edit, "template_sample_output_input", "Template sample output")
    assert_anchor(window.template_validate_button, "template_validate_button", "Validate template sample")
    assert_anchor(window.template_fill_sample_button, "template_fill_sample_button", "Fill template sample")
    assert_anchor(window.template_preflight_button, "template_preflight_button", "Run template preflight")
    assert_anchor(window.template_refresh_library_button, "template_refresh_library_button", "Refresh template library")
    assert_anchor(window.template_import_selected_button, "template_import_selected_button", "Import selected template")
    assert_anchor(window.template_open_library_button, "template_open_library_button", "Open template library directory")
    assert_anchor(window.template_library_search_edit, "template_library_search_input", "Template library search")
    assert_anchor(window.template_library_filter_combo, "template_library_filter_combo", "Template library filter")
    assert_anchor(window.template_library_sort_combo, "template_library_sort_combo", "Template library sort")
    assert_anchor(window.template_library_preflight_filter_combo, "template_library_preflight_filter_combo", "Template preflight filter")
    assert_anchor(window.template_library_time_filter_combo, "template_library_time_filter_combo", "Template time filter")
    assert_anchor(window.template_library_list, "template_library_list", "Template library list")


def test_settings_window_uses_project_drawn_frameless_chrome(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()

    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert window.settings_titlebar.objectName() == "settings_titlebar"
    assert window.settings_minimize_button.objectName() == "settings_minimize_button"
    assert window.settings_minimize_button.accessibleName() == "Minimize settings"
    assert window.settings_maximize_button.objectName() == "settings_maximize_button"
    assert window.settings_maximize_button.accessibleName() == "Maximize settings"
    assert window.settings_close_button.objectName() == "settings_close_button"
    assert window.settings_close_button.accessibleName() == "Close settings"
    assert window.settings_size_grip.objectName() == "settings_size_grip"
    assert window.settings_size_grip.accessibleName() == "Resize settings window"


def test_character_card_grid_reflows_without_horizontal_clipping_at_minimum_width(
    settings_config, make_settings_window
):
    characters = [
        {**DEFAULT_CHARACTER, "name": f"角色{index}", "sprites": [{"path": f"sprite-{index}.png"}]}
        for index in range(4)
    ]
    settings_config(characters=characters)
    window = make_settings_window()
    window.resize(800, 600)
    window.settings_tabs.setCurrentIndex(1)
    window.show()
    QApplication.processEvents()

    grid_width = window.character_card_grid.width()
    card_positions = [card.geometry() for card in window.character_card_frames]
    assert all(rect.left() >= 0 and rect.right() < grid_width for rect in card_positions)
    assert len({rect.left() for rect in card_positions}) == 2
    assert window.character_tab.widget.horizontalScrollBar().maximum() == 0

    window.resize(1200, 760)
    QApplication.processEvents()
    wide_positions = [card.geometry() for card in window.character_card_frames]
    assert len({rect.left() for rect in wide_positions}) > len({rect.left() for rect in card_positions})


def test_character_cards_are_square_image_forward_click_targets(settings_config, make_settings_window):
    settings_config(characters=[
        {
            **DEFAULT_CHARACTER,
            "name": "小雪",
            "avatar": "",
            "sprites": [{"path": "assets/sprites/xiaoxue-neutral.png"}],
        },
        {
            **DEFAULT_CHARACTER,
            "name": "铃音",
            "avatar": "assets/avatars/lingyin.png",
            "sprites": [],
        },
    ])
    window = make_settings_window()

    assert len(window.character_card_frames) == 2
    assert window.character_list.isHidden()

    first_card = window.character_card_frames[0]
    first_avatar = window.character_card_avatar_labels[0]
    first_button = window.character_card_buttons[0]

    assert first_card.objectName() == "character_card_0"
    assert first_card.minimumWidth() >= 220
    assert first_card.minimumHeight() > first_avatar.minimumHeight()
    assert first_card.minimumHeight() - first_avatar.minimumHeight() <= 240
    assert first_avatar.objectName() == "character_card_avatar_0"
    assert first_avatar.minimumWidth() >= 180
    assert first_avatar.minimumHeight() >= 190
    assert first_button.text() == "打开详情"
    assert first_avatar.text() == "头像"
    assert first_avatar.toolTip().endswith("xiaoxue-neutral.png")
    assert first_button.objectName() == "character_card_button_0"

    second_avatar = window.character_card_avatar_labels[1]
    assert second_avatar.toolTip().endswith("lingyin.png")

    window.char_name_edit.clear()
    QTest.mouseClick(second_avatar, Qt.MouseButton.LeftButton)

    assert window.char_name_edit.text() == "铃音"


def test_character_overview_page_uses_rich_cards_to_fill_the_first_layer(settings_config, make_settings_window):
    settings_config(characters=[
        {
            **DEFAULT_CHARACTER,
            "name": "小雪",
            "character_setting": "温柔可靠的见习骑士，擅长照顾玩家并推动日常剧情。",
            "sprites": [{"path": "neutral.png"}, {"path": "happy.png"}],
            "emotion_items": [
                {"id": 1, "label": "neutral", "sprite_path": "neutral.png"},
                {"id": 2, "label": "happy", "sprite_path": "happy.png"},
            ],
        },
        {
            **DEFAULT_CHARACTER,
            "name": "铃音",
            "character_setting": "安静敏锐的同伴。",
            "sprites": [],
            "emotion_items": [],
        },
    ])
    window = make_settings_window()

    assert window.character_overview_title_label.text() == "角色管理"
    assert "2 个角色" in window.character_overview_summary_label.text()
    assert "2 张立绘" in window.character_overview_summary_label.text()
    assert "2 个情绪绑定" in window.character_overview_summary_label.text()

    first_card = window.character_card_frames[0]
    first_avatar = window.character_card_avatar_labels[0]
    first_stats = window.character_card_stats_labels[0]

    assert not hasattr(window, "character_card_summary_labels")
    assert first_card.minimumWidth() >= 220
    assert first_card.minimumHeight() > first_avatar.minimumHeight()
    assert first_card.minimumHeight() - first_avatar.minimumHeight() <= 240
    assert first_avatar.minimumWidth() >= 180
    assert first_avatar.minimumHeight() >= 190
    assert window.character_card_buttons[0].text() == "打开详情"
    assert "2 张立绘" in first_stats.text()
    assert "2 个情绪" in first_stats.text()

    second_stats = window.character_card_stats_labels[1]
    assert "0 张立绘" in second_stats.text()
    assert "0 个情绪" in second_stats.text()

    window.character_card_buttons[0].click()
    assert window.character_stack.currentWidget() is window.character_detail_page


def test_character_management_uses_secondary_detail_page_flow(settings_config, make_settings_window):
    settings_config(characters=[
        {**DEFAULT_CHARACTER, "name": "小雪"},
        {**DEFAULT_CHARACTER, "name": "铃音"},
    ])
    window = make_settings_window()

    assert window.character_stack.objectName() == "character_stack"
    assert window.character_overview_page.objectName() == "character_overview_page"
    assert window.character_detail_page.objectName() == "character_detail_page"
    assert window.return_character_list_button.objectName() == "return_character_list_button"
    assert window.character_stack.currentWidget() is window.character_overview_page

    window.character_card_buttons[1].click()

    assert window.character_stack.currentWidget() is window.character_detail_page
    assert window.char_name_edit.text() == "铃音"

    window.return_character_list_button.click()

    assert window.character_stack.currentWidget() is window.character_overview_page


def test_mcp_tab_exposes_automation_anchors(settings_config, make_settings_window):
    settings_config()
    window = make_settings_window()

    def assert_anchor(widget, object_name: str, accessible_name: str):
        assert widget.objectName() == object_name
        assert widget.accessibleName() == accessible_name

    assert_anchor(window.mcp_redetect_button, "mcp_redetect_button", "Redetect MCP")
    assert_anchor(window.mcp_add_server_button, "mcp_add_server_button", "Add MCP server")
    assert_anchor(window.mcp_remove_server_button, "mcp_remove_server_button", "Remove selected MCP server")
    assert_anchor(window.mcp_test_server_button, "mcp_test_server_button", "Test selected MCP server")
    assert_anchor(window.mcp_summary_label, "mcp_summary_label", "MCP summary")
    assert_anchor(window.mcp_server_list, "mcp_server_list", "MCP server list")
    assert_anchor(window.mcp_detail_label, "mcp_detail_label", "MCP server detail")
    assert_anchor(window.mcp_name_edit, "mcp_name_input", "MCP server name")
    assert_anchor(window.mcp_transport_combo, "mcp_transport_combo", "MCP transport")
    assert_anchor(window.mcp_enabled_check, "mcp_enabled_checkbox", "MCP server enabled")
    assert_anchor(window.mcp_http_url_edit, "mcp_http_url_input", "MCP HTTP URL")
    assert_anchor(window.mcp_json_edit, "mcp_json_input", "MCP server JSON")
    assert_anchor(window.mcp_save_server_button, "mcp_save_server_button", "Save MCP server")
