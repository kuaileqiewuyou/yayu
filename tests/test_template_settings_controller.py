import ast
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from ui.settings_ui.template_controller import (
    TemplateLibraryWorkflow,
    TemplatePackageWorkflow,
    TemplatePublishDraftWorkflow,
    TemplateReleaseArtifactWorkflow,
    TemplateSaveWorkflow,
    TemplateSettingsController,
)


class FixedDateTime(datetime):
    @classmethod
    def now(cls):
        return cls(2026, 5, 26, 20, 59, 0)


def test_template_controller_sanitizes_draft_filename_like_settings_window():
    assert TemplateSettingsController.safe_template_draft_filename(" 小雪/测试:角色 ") == "小雪测试角色-publish-draft.md"
    assert TemplateSettingsController.safe_template_draft_filename("   ") == "template-publish-draft.md"


def test_template_controller_sanitizes_release_package_dir_name_like_settings_window():
    assert TemplateSettingsController.make_template_release_package_dir_name(
        '诺艾尔:/?* "', now=FixedDateTime.now
    ) == "诺艾尔-template-package-2026-05-26-205900"
    assert TemplateSettingsController.make_template_release_package_dir_name(
        "   ", now=FixedDateTime.now
    ) == "template-package-2026-05-26-205900"


def test_template_controller_lists_sample_token_coverage_like_settings_window():
    sample = "\n".join([
        '{"character_name":"CG","speech":"夕阳下的教室","sprite":"-1"}',
        '{"character_name":"诺艾尔","speech":"你好","sprite":"0"}',
        '{"character_name":"NARR","speech":"风吹过窗边。","sprite":"-1"}',
        '{"character_name":"STAT","speech":"好感度+1","sprite":"-1"}',
        '{"character_name":"CHOICE","speech":"留下/离开","sprite":"-1"}',
        "not-json",
    ])

    assert TemplateSettingsController.template_sample_token_coverage_list(sample) == [
        "NARR",
        "CHOICE",
        "STAT",
        "CG",
    ]
    assert TemplateSettingsController.template_sample_token_coverage_list("not-json\n") == []


def test_template_controller_formats_sample_validation_results_like_settings_window():
    assert TemplateSettingsController.template_validation_result_message("   ") == (
        "error",
        "请先粘贴一段示例输出。",
    )

    error_and_warning_sample = "\n".join([
        '{"character_name":"诺艾尔","speech":"你好"}',
        '{"character_name":"CG","speech":"","sprite":"夕阳下的教室"}',
    ])
    assert TemplateSettingsController.template_validation_result_message(error_and_warning_sample) == (
        "error",
        "\n".join([
            "示例输出有错误：",
            "第 1 行：缺少必填字段: sprite",
            "警告：",
            "第 2 行：CG 的 prompt 应放在 speech，不要放在 sprite",
        ]),
    )

    warning_sample = '{"character_name":"CG","speech":"","sprite":"夕阳下的教室"}'
    assert TemplateSettingsController.template_validation_result_message(warning_sample) == (
        "warning",
        "\n".join([
            "示例输出可用，但有警告：",
            "第 1 行：CG 的 prompt 应放在 speech，不要放在 sprite",
        ]),
    )

    ok_sample = '{"character_name":"诺艾尔","speech":"你好","sprite":"0"}'
    assert TemplateSettingsController.template_validation_result_message(ok_sample) == (
        "ok",
        "示例输出校验通过。",
    )


def test_settings_window_template_validation_method_delegates_result_formatting_to_controller():
    window_path = Path(__file__).resolve().parents[1] / "ui" / "settings_ui" / "window.py"
    source = window_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    settings_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SettingsWindow")
    method = next(
        node
        for node in settings_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "_validate_template_sample_output"
    )
    method_source = ast.get_source_segment(source, method) or ""

    assert "TemplateSettingsController.template_validation_result_message" in method_source
    assert "validate_template_output(" not in method_source
    assert "示例输出有错误" not in method_source
    assert "示例输出可用，但有警告" not in method_source


def test_template_controller_builds_preflight_fix_suggestions_like_settings_window():
    errors = [
        "角色名称不能为空",
        "第 1 行：缺少必填字段：sprite",
        "缺少示例输出",
    ]
    warnings = ["角色设定较短", "情绪标签为空"]

    suggestions = TemplateSettingsController.template_preflight_fix_suggestions(errors, warnings)

    assert suggestions == [
        "填写角色名称，例如：诺艾尔。",
        '补齐对应 JSON 对象的必填字段，例如 sprite；如果不切换立绘可填 "-1"。',
        "点击“填入示例”生成一份可用 JSON-lines 后再修改。",
        "补充角色性格、称呼方式和对话边界，方便模型稳定保持人设。",
        "补充情绪标签，例如：0: neutral、1: happy。",
        "优先先修错误，再回头处理警告。",
        '重新点击“发布前检查”确认状态是否变为“通过”或“有警告”。',
    ]


def test_template_controller_builds_warning_only_preflight_fix_suggestions_like_settings_window():
    suggestions = TemplateSettingsController.template_preflight_fix_suggestions(
        [],
        ["角色设定为空", "CG 的 prompt 应放在 speech"],
    )

    assert suggestions == [
        "补充角色性格、称呼方式和对话边界，方便模型稳定保持人设。",
        '把 CG prompt 放到 speech，并将 sprite 设为 "-1"。',
        "如果暂时不修，也建议在分享给 reviewer 前至少再复查一次。",
        '重新点击“发布前检查”确认警告是否减少。',
    ]


def test_template_controller_builds_preflight_report_like_settings_window():
    level, message = TemplateSettingsController.build_template_preflight_report(
        character_name="诺艾尔",
        character_setting="可靠的女仆骑士，会认真回应玩家并推进日常剧情。",
        emotion_tags="0: neutral\n1: happy",
        sample_output='{"character_name":"NARR","speech":"清晨的风吹进房间。","sprite":"-1"}',
    )

    assert level == "ok"
    assert "发布前检查通过" in message
    assert "角色名称：诺艾尔" in message
    assert "示例输出：1 行" in message
    assert "修复建议：" not in message
    assert "建议继续生成发布清单或导出发布包" in message
    assert "如需写入角色配置，请记得点击“保存配置”" in message


def test_template_controller_builds_preflight_report_errors_like_settings_window():
    level, message = TemplateSettingsController.build_template_preflight_report(
        character_name="",
        character_setting="短",
        emotion_tags="",
        sample_output='{"character_name":"诺艾尔","speech":"你好"}',
    )

    assert level == "error"
    assert "发布前检查未通过" in message
    assert "角色名称：未填写" in message
    assert "角色名称不能为空" in message
    assert "缺少必填字段" in message
    assert "修复建议：" in message
    assert "填写角色名称，例如：诺艾尔" in message
    assert "补齐对应 JSON 对象的必填字段，例如 sprite" in message


def test_template_controller_builds_publish_handoff_report_from_explicit_inputs_and_preflight_tuple():
    character_setting = "认真可靠的见习骑士，负责陪伴玩家完成日常对话。"
    sample_output = "\n".join([
        '{"character_name":"NARR","speech":"清晨的风吹进房间。","sprite":"-1"}',
        '{"character_name":"诺艾尔","speech":"我会认真守护这里。","sprite":"0"}',
        '{"character_name":"CG","speech":"夕阳下的教室","sprite":"-1"}',
    ])
    preflight = (
        "warning",
        "发布前检查可用，但有警告：\n角色名称：诺艾尔\n示例输出：3 行\n警告：\n- 角色设定较短",
    )

    level, report = TemplateSettingsController.build_template_publish_handoff_report(
        character_name=" 诺艾尔 ",
        character_setting=character_setting,
        emotion_tags="0: neutral\n\n1: happy",
        sample_output=sample_output,
        preflight=preflight,
    )

    assert level == "warning"
    assert report == "\n".join([
        "角色模板发布清单：",
        "角色名称：诺艾尔",
        f"角色设定：{len(character_setting)} 字",
        "情绪标签：2 行",
        "示例输出：3 行",
        "控制 token 覆盖：NARR、CG",
        "发布前检查：有警告",
        "边界：这是轻量交接清单，不是完整模板市场、多示例管理或正式发布工作流。",
        "发布前检查摘要：",
        preflight[1],
    ])


def test_template_controller_builds_publish_draft_markdown_from_explicit_inputs():
    character_setting = "认真可靠的见习骑士，负责陪伴玩家完成日常对话。"
    sample_output = "\n".join([
        '{"character_name":"NARR","speech":"清晨的风吹进房间。","sprite":"-1"}',
        '{"character_name":"诺艾尔","speech":"我会认真守护这里。","sprite":"0"}',
        '{"character_name":"CG","speech":"夕阳下的教室","sprite":"-1"}',
    ])
    preflight = (
        "ok",
        "发布前检查通过。\n角色名称：诺艾尔\n示例输出：3 行\n未发现错误或警告。",
    )
    handoff_report = "角色模板发布清单：\n角色名称：诺艾尔\n发布前检查：通过"

    level, markdown = TemplateSettingsController.build_template_publish_draft_markdown(
        character_name=" 诺艾尔 ",
        character_setting=character_setting,
        emotion_tags="0: neutral\n1: happy",
        sample_output=f"\n{sample_output}\n",
        preflight=preflight,
        handoff_report=handoff_report,
        generated_at="2026-05-26 20:59:00",
    )

    assert level == "ok"
    assert markdown == "\n".join([
        "# 角色模板发布草稿：诺艾尔",
        "",
        "生成时间：2026-05-26 20:59:00",
        "",
        "## 角色信息",
        "",
        "- 角色名称：诺艾尔",
        f"- 角色设定长度：{len(character_setting)} 字",
        "- 情绪标签行数：2 行",
        "- 示例输出行数：3 行",
        "- 控制 token 覆盖：NARR、CG",
        "- 发布前检查：通过",
        "",
        "## 角色设定",
        "",
        character_setting,
        "",
        "## 情绪标签",
        "",
        "```text",
        "0: neutral\n1: happy",
        "```",
        "",
        "## 示例输出 JSON-lines",
        "",
        "```jsonl",
        sample_output,
        "```",
        "",
        "## 发布前检查摘要",
        "",
        preflight[1],
        "",
        "## 轻量发布清单",
        "",
        handoff_report,
        "",
        "## 边界",
        "",
        "这是本地轻量发布草稿，用于 reviewer/维护者交接；不是完整模板市场、多示例管理或正式发布工作流。",
        "",
    ])


def test_template_controller_builds_release_package_metadata_from_explicit_inputs():
    character_setting = "认真可靠的见习骑士，负责陪伴玩家完成日常对话。"
    sample_output = "\n".join([
        '{"character_name":"NARR","speech":"清晨的风吹进房间。","sprite":"-1"}',
        '{"character_name":"诺艾尔","speech":"我会认真守护这里。","sprite":"0"}',
        '{"character_name":"CG","speech":"夕阳下的教室","sprite":"-1"}',
    ])

    metadata = TemplateSettingsController.build_template_release_package_metadata(
        character_name=" 诺艾尔 ",
        character_setting=character_setting,
        emotion_tags="0: neutral\n\n1: happy",
        sample_output=f"\n{sample_output}\n",
        preflight_level="warning",
        exported_at="2026-05-26T20:59:00",
    )

    assert metadata == {
        "schema_version": 1,
        "package_type": "galgame_agent.character_template.release_package",
        "character_name": "诺艾尔",
        "exported_at": "2026-05-26T20:59:00",
        "preflight_level": "warning",
        "preflight_status": "有警告",
        "character_setting_length": len(character_setting),
        "emotion_tag_lines": 2,
        "sample_output_lines": 3,
        "token_coverage": ["NARR", "CG"],
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


def test_template_controller_builds_release_package_files_from_explicit_inputs():
    metadata = {
        "schema_version": 1,
        "package_type": "galgame_agent.character_template.release_package",
        "character_name": "诺艾尔",
        "exported_at": "2026-05-26T20:59:00",
        "preflight_level": "warning",
        "preflight_status": "有警告",
        "character_setting_length": 23,
        "emotion_tag_lines": 2,
        "sample_output_lines": 2,
        "token_coverage": ["NARR"],
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
    raw_sample = (
        "\n"
        '  {"character_name":"诺艾尔","speech":"你好","sprite":"0"}  \n'
        "\n"
        '  {"character_name":"NARR","speech":"风吹过窗边。","sprite":"-1"}  '
    )
    draft = "# 角色模板发布草稿：诺艾尔\n"
    preflight_report = "发布前检查可用，但有警告：\n角色名称：诺艾尔"

    workflow = TemplateReleaseArtifactWorkflow(now=lambda: datetime(2026, 7, 10, 15, 30, 0))
    workflow_level, workflow_draft, workflow_metadata, workflow_files = workflow.build(
        character_name=" 诺艾尔 ",
        character_setting="认真可靠的见习骑士，负责陪伴玩家完成日常对话。",
        emotion_tags="0: neutral\n1: happy",
        sample_output=raw_sample,
        preflight_level="warning",
        preflight_report=preflight_report,
        handoff_report="角色模板发布清单：有警告",
    )

    assert workflow_level == "warning"
    assert "角色模板发布草稿：诺艾尔" in workflow_draft
    assert workflow_metadata["exported_at"] == "2026-07-10T15:30:00"
    assert workflow_files["角色模板发布草稿.md"] == workflow_draft
    assert '"character_name": "诺艾尔"' in workflow_files["template-data.json"]

    level, files = TemplateSettingsController.build_template_release_package_files(
        metadata=metadata,
        draft=draft,
        preflight_report=preflight_report,
        character_name=" 诺艾尔 ",
        character_setting="认真可靠的见习骑士，负责陪伴玩家完成日常对话。",
        emotion_tags="0: neutral\n1: happy",
        sample_output_raw=raw_sample,
    )

    assert level == "warning"
    assert list(files) == [
        "README.md",
        "角色模板发布草稿.md",
        "template-output.jsonl",
        "preflight-report.txt",
        "metadata.json",
        "template-data.json",
    ]
    assert "# 角色模板发布包：诺艾尔" in files["README.md"]
    assert "导出时间：2026-05-26T20:59:00" in files["README.md"]
    assert "发布前检查：有警告" in files["README.md"]
    assert "控制 token 覆盖：NARR" in files["README.md"]
    assert files["角色模板发布草稿.md"] == draft
    assert files["template-output.jsonl"] == raw_sample + "\n"
    assert files["preflight-report.txt"] == preflight_report + "\n"
    assert json.loads(files["metadata.json"]) == metadata
    template_data = json.loads(files["template-data.json"])
    assert template_data == {
        "schema_version": 1,
        "package_type": "galgame_agent.character_template.import_data",
        "character_name": "诺艾尔",
        "character_setting": "认真可靠的见习骑士，负责陪伴玩家完成日常对话。",
        "emotion_tags": "0: neutral\n1: happy",
        "sample_output": raw_sample + "\n",
    }


def test_template_controller_builds_sample_output_variants_like_settings_window():
    review = TemplateSettingsController.build_template_sample_output(" 诺艾尔 ", "模板复用示例")
    review_lines = [json.loads(line) for line in review.splitlines()]

    assert [line["character_name"] for line in review_lines] == ["NARR", "诺艾尔", "STAT", "CHOICE"]
    assert "模板库" in review_lines[0]["speech"]
    assert "复核" in review_lines[1]["speech"]
    assert "模板包" in review_lines[2]["speech"]
    assert "/" in review_lines[3]["speech"]

    repair = TemplateSettingsController.build_template_sample_output("", "模板修正示例")
    repair_lines = [json.loads(line) for line in repair.splitlines()]

    assert [line["character_name"] for line in repair_lines] == ["NARR", "小雪", "STAT", "CHOICE"]
    assert "警告" in repair_lines[0]["speech"] or "修复" in repair_lines[0]["speech"]
    assert "修正" in repair_lines[1]["speech"] or "补齐" in repair_lines[1]["speech"]
    assert "复查" in repair_lines[2]["speech"] or "重新检查" in repair_lines[2]["speech"]
    assert "/" in repair_lines[3]["speech"]

    full = TemplateSettingsController.build_template_sample_output("诺艾尔", "完整示例")
    full_lines = [json.loads(line) for line in full.splitlines()]
    assert [line["character_name"] for line in full_lines] == ["诺艾尔", "NARR", "CHOICE", "STAT", "CG"]
    assert full_lines[-1]["sprite"] == "-1"


def test_template_controller_builds_library_result_summary_text_like_settings_window():
    summaries = [
        SimpleNamespace(importable=True),
        SimpleNamespace(importable=True),
        SimpleNamespace(importable=False),
    ]

    assert TemplateSettingsController.template_library_result_summary_text(summaries) == "共 3 个模板：2 个可导入，1 个不可导入"
    assert TemplateSettingsController.template_library_result_summary_text(
        summaries[:1], search_text="芙宁"
    ) == "当前筛选结果：1 个模板（可导入 1 个）"
    assert TemplateSettingsController.template_library_result_summary_text(
        summaries[2:], filter_text="只看不可导入"
    ) == "当前筛选结果：1 个模板（不可导入 1 个）"
    assert TemplateSettingsController.template_library_result_summary_text(
        [], preflight_filter_text="只看通过"
    ) == "当前筛选结果：0 个模板"
    assert TemplateSettingsController.template_library_result_summary_text(
        summaries, time_filter_text="最近 1 天"
    ) == "当前筛选结果：3 个模板（可导入 2 个，不可导入 1 个）"


def test_template_library_workflow_opens_library_directory_via_injected_io(tmp_path):
    root = tmp_path / "packages"
    made = []
    opened = []
    workflow = TemplateLibraryWorkflow(
        lambda: root,
        lambda _root: [],
        ensure_directory=lambda path: made.append(path),
        open_directory=lambda path: opened.append(path),
    )

    opened_path = workflow.open_library_directory()

    assert opened_path == root
    assert made == [root]
    assert opened == [root]


def test_template_library_workflow_owns_visible_state_and_selection():
    summaries = [
        SimpleNamespace(
            character_name="旧模板",
            is_valid=True,
            importable=True,
            preflight_status="通过",
            exported_at="2026-06-13T12:00:00",
            token_coverage=("NARR",),
            path=Path("old"),
            missing_files=(),
            reason="",
        ),
        SimpleNamespace(
            character_name="新模板",
            is_valid=True,
            importable=True,
            preflight_status="有警告",
            exported_at="2026-06-14T12:00:00",
            token_coverage=("CHOICE",),
            path=Path("new"),
            missing_files=(),
            reason="",
        ),
    ]
    workflow = TemplateLibraryWorkflow(lambda: Path("packages"), lambda _root: summaries)

    state = workflow.refresh(search_text="新")

    assert state.rows == ["新模板｜可导入｜有警告｜CHOICE｜2026-06-14T12:00:00"]
    assert state.result_summary == "当前筛选结果：1 个模板（可导入 1 个）"
    assert "角色名称：新模板" in state.detail_text
    assert state.import_enabled is True
    assert workflow.visible_summaries == [summaries[1]]
    selected, error = workflow.import_selection(0)
    assert selected is summaries[1]
    assert error is None

    loaded_paths = []
    import_data, error = workflow.load_import_selection(
        0,
        lambda path: loaded_paths.append(path) or SimpleNamespace(character_name="新模板"),
    )
    assert import_data.character_name == "新模板"
    assert loaded_paths == [Path("new")]
    assert error is None

    class Editor:
        char_name_edit = SimpleNamespace(setText=lambda value: setattr(Editor, "name", value))
        char_setting_edit = SimpleNamespace(setPlainText=lambda value: setattr(Editor, "setting", value))
        emotion_tags_edit = SimpleNamespace(setPlainText=lambda value: setattr(Editor, "emotions", value))
        template_sample_output_edit = SimpleNamespace(setPlainText=lambda value: setattr(Editor, "sample", value))

    completed = workflow.complete_import(
        Editor,
        SimpleNamespace(
            character_name="新模板",
            character_setting="新设定",
            emotion_tags="0: neutral",
            sample_output="{}\n",
        ),
        validate=lambda: "模板示例输出可用，但有警告。",
    )
    assert completed.validation_message == "模板示例输出可用，但有警告。"
    assert "已导入模板：新模板" in completed.status_message
    assert "仍有警告" in completed.status_message
    assert Editor.name == "新模板"
    assert Editor.setting == "新设定"


def test_template_controller_filters_and_sorts_library_summaries_like_settings_window():
    summaries = [
        SimpleNamespace(character_name="诺艾尔", importable=True, preflight_status="通过", exported_at="2026-06-13T12:00:00"),
        SimpleNamespace(character_name="invalid-package", importable=False, preflight_status="未通过", exported_at=""),
        SimpleNamespace(character_name="芙宁娜", importable=True, preflight_status="有警告", exported_at="2026-06-14T08:30:00"),
    ]

    def names(**kwargs):
        return [
            summary.character_name
            for summary in TemplateSettingsController.filtered_template_library_summaries(
                summaries,
                now=lambda: datetime(2026, 6, 15, 8, 30, 0),
                **kwargs,
            )
        ]

    assert names() == ["芙宁娜", "诺艾尔", "invalid-package"]
    assert names(sort_text="按名称") == ["invalid-package", "芙宁娜", "诺艾尔"]
    assert names(search_text="芙宁") == ["芙宁娜"]
    assert names(filter_text="只看不可导入") == ["invalid-package"]
    assert names(filter_text="只看可导入") == ["芙宁娜", "诺艾尔"]
    assert names(preflight_filter_text="只看通过") == ["诺艾尔"]
    assert names(preflight_filter_text="只看有警告") == ["芙宁娜"]
    assert names(time_filter_text="最近 1 天") == ["芙宁娜"]


def test_template_controller_recent_day_filter_uses_current_time_instead_of_fixed_date():
    summaries = [
        SimpleNamespace(character_name="过期模板", importable=True, preflight_status="通过", exported_at="2026-06-14T08:30:00"),
        SimpleNamespace(character_name="近期模板", importable=True, preflight_status="通过", exported_at="2026-07-08T12:00:00"),
        SimpleNamespace(character_name="坏时间模板", importable=True, preflight_status="通过", exported_at="not-a-date"),
        SimpleNamespace(character_name="无时间模板", importable=True, preflight_status="通过", exported_at=""),
    ]

    filtered = TemplateSettingsController.filtered_template_library_summaries(
        summaries,
        time_filter_text="最近 1 天",
        now=lambda: datetime(2026, 7, 8, 13, 0, 0),
    )

    assert [summary.character_name for summary in filtered] == ["近期模板"]


def test_template_controller_builds_library_row_text_like_settings_window():
    importable = SimpleNamespace(
        character_name="诺艾尔",
        is_valid=True,
        importable=True,
        preflight_status="通过",
        token_coverage=("NARR", "CHOICE"),
        exported_at="2026-06-14T08:30:00",
        reason="",
    )
    importable_without_tokens = SimpleNamespace(
        character_name="小雪",
        is_valid=True,
        importable=True,
        preflight_status="有警告",
        token_coverage=(),
        exported_at="unknown-time",
        reason="",
    )
    blocked = SimpleNamespace(
        character_name="broken-package",
        is_valid=False,
        importable=False,
        preflight_status="未通过",
        token_coverage=(),
        exported_at="",
        reason="missing metadata.json",
    )

    assert TemplateSettingsController.template_library_row_text(importable) == "诺艾尔｜可导入｜通过｜NARR/CHOICE｜2026-06-14T08:30:00"
    assert TemplateSettingsController.template_library_row_text(importable_without_tokens) == "小雪｜可导入｜有警告｜no-tokens｜unknown-time"
    assert TemplateSettingsController.template_library_row_text(blocked) == "broken-package｜不可导入｜missing metadata.json"


def test_template_controller_builds_empty_library_detail_text_like_settings_window():
    assert TemplateSettingsController.template_library_empty_detail_text("") == (
        "暂无本地模板。\n下一步建议：先保存到模板库，或打开模板库目录检查是否有可用发布包。"
    )
    assert TemplateSettingsController.template_library_empty_detail_text(" 芙宁 ") == (
        "没有匹配的本地模板。\n下一步建议：调整搜索关键词，或清空搜索后重新选择模板。"
    )


def test_template_controller_builds_library_detail_text_like_settings_window():
    importable = SimpleNamespace(
        character_name="诺艾尔",
        importable=True,
        preflight_status="通过",
        path="D:/templates/noelle",
        token_coverage=("NARR", "CHOICE"),
        missing_files=(),
        reason="",
    )
    blocked = SimpleNamespace(
        character_name="broken-package",
        importable=False,
        preflight_status="未通过",
        path="D:/templates/broken",
        token_coverage=(),
        missing_files=("metadata.json", "template-data.json"),
        reason="missing metadata.json",
    )

    assert TemplateSettingsController.template_library_detail_text(importable) == "\n".join([
        "角色名称：诺艾尔",
        "导入状态：可导入",
        "发布前检查：通过",
        "路径：D:/templates/noelle",
        "控制 token 覆盖：NARR、CHOICE",
        "下一步建议：可直接导入到当前编辑区，并在保存前重新确认配置。",
    ])
    assert TemplateSettingsController.template_library_detail_text(blocked) == "\n".join([
        "角色名称：broken-package",
        "导入状态：不可导入",
        "发布前检查：未通过",
        "路径：D:/templates/broken",
        "缺失文件：metadata.json, template-data.json",
        "原因：missing metadata.json",
        "下一步建议：先补齐缺失文件或重新导出发布包，再回来刷新模板库。",
    ])


def test_template_controller_builds_library_selection_state_like_settings_window():
    importable = SimpleNamespace(
        character_name="诺艾尔",
        importable=True,
        preflight_status="通过",
        path="D:/templates/noelle",
        token_coverage=("NARR", "CHOICE"),
        missing_files=(),
        reason="",
    )
    blocked = SimpleNamespace(
        character_name="broken-package",
        importable=False,
        preflight_status="未通过",
        path="D:/templates/broken",
        token_coverage=(),
        missing_files=("metadata.json",),
        reason="missing metadata.json",
    )

    detail_text, import_enabled = TemplateSettingsController.template_library_selection_state(
        [importable, blocked],
        0,
    )
    assert "角色名称：诺艾尔" in detail_text
    assert "导入状态：可导入" in detail_text
    assert import_enabled is True

    detail_text, import_enabled = TemplateSettingsController.template_library_selection_state(
        [importable, blocked],
        1,
    )
    assert "角色名称：broken-package" in detail_text
    assert "导入状态：不可导入" in detail_text
    assert import_enabled is False

    detail_text, import_enabled = TemplateSettingsController.template_library_selection_state(
        [importable, blocked],
        -1,
    )
    assert detail_text == "暂无本地模板。"
    assert import_enabled is False

    detail_text, import_enabled = TemplateSettingsController.template_library_selection_state(
        [importable, blocked],
        2,
    )
    assert detail_text == "暂无本地模板。"
    assert import_enabled is False


def test_template_controller_selects_importable_template_summary_like_settings_window():
    importable = SimpleNamespace(character_name="诺艾尔", importable=True, path="D:/templates/noelle")
    blocked = SimpleNamespace(character_name="broken-package", importable=False, path="D:/templates/broken")

    summary, error_message = TemplateSettingsController.template_library_import_selection(
        [importable, blocked],
        0,
    )
    assert summary is importable
    assert error_message is None

    summary, error_message = TemplateSettingsController.template_library_import_selection(
        [importable, blocked],
        1,
    )
    assert summary is None
    assert error_message == "请先选择一个可导入模板。"

    summary, error_message = TemplateSettingsController.template_library_import_selection(
        [importable, blocked],
        -1,
    )
    assert summary is None
    assert error_message == "请先选择一个可导入模板。"

    summary, error_message = TemplateSettingsController.template_library_import_selection(
        [importable, blocked],
        2,
    )
    assert summary is None
    assert error_message == "请先选择一个可导入模板。"


def test_template_controller_builds_import_confirmation_message_like_settings_window():
    assert TemplateSettingsController.template_library_import_confirmation_message() == (
        "导入选中模板会覆盖当前角色名称、角色设定、情绪标签和示例输出。\n"
        "导入后会自动重新校验示例输出，但不会自动保存配置。\n"
        "如果确认无误，请在导入后继续点击“保存配置”。\n\n是否继续？"
    )


def test_template_controller_applies_import_data_to_editor_like_settings_window():
    calls = []

    class FakeLineEdit:
        def setText(self, value):
            calls.append(("char_name", "setText", value))

    class FakePlainTextEdit:
        def __init__(self, name):
            self.name = name

        def setPlainText(self, value):
            calls.append((self.name, "setPlainText", value))

    editor = SimpleNamespace(
        char_name_edit=FakeLineEdit(),
        char_setting_edit=FakePlainTextEdit("char_setting"),
        emotion_tags_edit=FakePlainTextEdit("emotion_tags"),
        template_sample_output_edit=FakePlainTextEdit("template_sample_output"),
    )
    import_data = SimpleNamespace(
        character_name="诺艾尔",
        character_setting="认真可靠的见习骑士。",
        emotion_tags="0: neutral\n1: happy",
        sample_output='{"character_name":"诺艾尔","speech":"你好","sprite":"0"}\n',
    )

    TemplateSettingsController.apply_template_import_data_to_editor(editor, import_data)

    assert calls == [
        ("char_name", "setText", "诺艾尔"),
        ("char_setting", "setPlainText", "认真可靠的见习骑士。"),
        ("emotion_tags", "setPlainText", "0: neutral\n1: happy"),
        ("template_sample_output", "setPlainText", '{"character_name":"诺艾尔","speech":"你好","sprite":"0"}\n'),
    ]


def test_template_controller_builds_import_status_message_like_settings_window():
    assert TemplateSettingsController.template_import_status_message(
        "诺艾尔",
        "示例输出校验通过。",
    ) == (
        "已导入模板：诺艾尔。示例输出已自动重新校验，建议继续点击“保存配置”。\n"
        "如需交接，也可以继续生成发布清单或导出发布包。"
    )
    assert TemplateSettingsController.template_import_status_message(
        "诺艾尔",
        "示例输出可用，但有警告：\n第 1 行：CG 的 prompt 应放在 speech",
    ) == (
        "已导入模板：诺艾尔。当前示例输出仍有警告，建议先修正后再保存配置或分享给 reviewer。\n"
        "如需继续交接，也可以生成发布清单或导出发布包。"
    )


def test_settings_window_template_import_forwarder_keeps_dialog_cancel_branch_and_delegates_editor_writes():
    window_path = Path(__file__).resolve().parents[1] / "ui" / "settings_ui" / "window.py"
    source = window_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    settings_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SettingsWindow")
    method = next(
        node
        for node in settings_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "_import_selected_template_library_package"
    )
    method_source = ast.get_source_segment(source, method)

    assert "if answer != QMessageBox.StandardButton.Yes:" in method_source
    assert "return" in method_source.split("if answer != QMessageBox.StandardButton.Yes:", 1)[1].split("import_data", 1)[0]
    assert "self.template_library_workflow.import_selection(row)" in method_source
    assert "TemplateSettingsController.template_library_import_confirmation_message()" in method_source
    assert "self.template_library_workflow.complete_import(" in method_source
    assert "TemplateSettingsController.apply_template_import_data_to_editor(self, import_data)" not in method_source
    assert "char_name_edit.setText(import_data.character_name)" not in method_source
    assert "char_setting_edit.setPlainText(import_data.character_setting)" not in method_source
    assert "emotion_tags_edit.setPlainText(import_data.emotion_tags)" not in method_source
    assert "template_sample_output_edit.setPlainText(import_data.sample_output)" not in method_source


def test_template_save_workflow_owns_preflight_gate_and_warning_status():
    calls = []
    workflow = TemplateSaveWorkflow()

    blocked = workflow.run(
        preflight=lambda: ("error", "missing sample"),
        save=lambda: calls.append("save"),
        saved_status=lambda: ("saved", False),
    )
    warning = workflow.run(
        preflight=lambda: ("warning", "review sample"),
        save=lambda: calls.append("save"),
        saved_status=lambda: ("saved", False),
    )

    assert calls == ["save"]
    assert blocked.saved is False
    assert blocked.preflight_message == "missing sample"
    assert blocked.status_message == "保存已取消：发布前检查未通过。\nmissing sample"
    assert blocked.is_error is True
    assert warning.saved is True
    assert warning.status_message == "saved\n角色模板发布前检查有警告，建议查看发布前检查。"
    assert warning.is_error is False


def test_template_publish_draft_workflow_writes_success_and_preserves_failure():
    writes = []
    workflow = TemplatePublishDraftWorkflow(
        write_text_file=lambda path, text: writes.append((Path(path), text)),
    )

    warning = workflow.write(
        path=Path("exports/character-draft.md"),
        markdown="# draft",
        level="warning",
    )

    assert warning.error is None
    assert warning.message == (
        "已导出发布草稿：exports\\character-draft.md\n发布前检查有警告，建议导出后继续修正。"
    ) or warning.message == (
        "已导出发布草稿：exports/character-draft.md\n发布前检查有警告，建议导出后继续修正。"
    )
    assert writes == [(Path("exports/character-draft.md"), "# draft")]

    failed = TemplatePublishDraftWorkflow(
        write_text_file=lambda _path, _text: (_ for _ in ()).throw(OSError("disk full")),
    ).write(
        path=Path("exports/broken.md"),
        markdown="# broken",
        level="ok",
    )

    assert isinstance(failed.error, OSError)
    assert failed.message == "导出发布草稿失败：disk full"


def test_template_package_workflow_uses_default_filesystem_adapters(tmp_path):
    package_dir = tmp_path / "package"
    workflow = TemplatePackageWorkflow()

    result = workflow.write(
        root=tmp_path,
        package_name="package",
        files={"README.md": "readme", "metadata.json": "{}"},
        level="ok",
        action="export",
    )

    assert result.error is None
    assert (package_dir / "README.md").read_text(encoding="utf-8") == "readme"
    assert (package_dir / "metadata.json").read_text(encoding="utf-8") == "{}"


def test_template_package_workflow_writes_export_and_library_packages():
    files = {"README.md": "readme", "metadata.json": "{}"}
    made = []
    written = []
    workflow = TemplatePackageWorkflow(
        make_directory=lambda path: made.append(path),
        write_text_file=lambda path, text: written.append((Path(path), text)),
    )

    export_result = workflow.write(
        action="export",
        root=Path("exports"),
        package_name="character-package",
        files=files,
        level="warning",
    )
    library_result = workflow.write(
        action="library",
        root=Path("library"),
        package_name="character-package",
        files=files,
        level="ok",
    )

    assert export_result.error is None
    assert export_result.package_dir == Path("exports/character-package")
    assert "已导出发布包" in export_result.message
    assert "有警告" in export_result.message
    assert library_result.error is None
    assert library_result.message == "已保存到模板库：library\\character-package" or library_result.message == "已保存到模板库：library/character-package"
    assert made == [
        Path("exports/character-package"),
        Path("library"),
        Path("library/character-package"),
    ]
    assert written == [
        (Path("exports/character-package/README.md"), "readme"),
        (Path("exports/character-package/metadata.json"), "{}"),
        (Path("library/character-package/README.md"), "readme"),
        (Path("library/character-package/metadata.json"), "{}"),
    ]


def test_template_package_workflow_preserves_write_failure_result():
    workflow = TemplatePackageWorkflow(
        make_directory=lambda _path: None,
        write_text_file=lambda _path, _text: (_ for _ in ()).throw(OSError("disk full")),
    )

    result = workflow.write(
        action="export",
        root=Path("exports"),
        package_name="character-package",
        files={"README.md": "readme"},
        level="ok",
    )

    assert isinstance(result.error, OSError)
    assert "disk full" in result.message
    assert result.package_dir == Path("exports/character-package")


def test_template_controller_builds_package_write_success_and_error_messages_like_settings_window():
    package_dir = Path("D:/exports/诺艾尔-template-package")

    assert TemplateSettingsController.template_package_write_success_message(
        action="export",
        package_dir=package_dir,
        level="ok",
    ) == f"已导出发布包：{package_dir}"
    assert TemplateSettingsController.template_package_write_success_message(
        action="export",
        package_dir=package_dir,
        level="warning",
    ) == f"已导出发布包：{package_dir}\n发布前检查有警告，建议导出后继续修正。"
    assert TemplateSettingsController.template_package_write_success_message(
        action="library",
        package_dir=package_dir,
        level="warning",
    ) == f"已保存到模板库：{package_dir}\n发布前检查有警告，建议保存后继续修正。"
    assert TemplateSettingsController.template_package_write_error_message(
        action="export",
        error=OSError("disk full"),
        package_dir=package_dir,
    ) == f"导出发布包失败：disk full\n目标路径：{package_dir}"
    assert TemplateSettingsController.template_package_write_error_message(
        action="library",
        error=OSError("denied"),
        package_dir=package_dir,
    ) == f"保存到模板库失败：denied\n目标路径：{package_dir}"


def test_settings_window_template_package_write_messages_delegate_to_controller():
    window_path = Path(__file__).resolve().parents[1] / "ui" / "settings_ui" / "window.py"
    source = window_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    settings_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SettingsWindow")
    methods = {
        node.name: ast.get_source_segment(source, node) or ""
        for node in settings_class.body
        if isinstance(node, ast.FunctionDef)
    }
    combined_source = methods["_export_template_release_package"] + methods["_save_template_to_library"]

    assert combined_source.count("self.template_package_workflow.write(") == 2
    assert "TemplateSettingsController.template_package_write_success_message(" not in combined_source
    assert "TemplateSettingsController.template_package_write_error_message(" not in combined_source
    assert "已导出发布包" not in combined_source
    assert "已保存到模板库" not in combined_source
    assert "发布前检查有警告，建议导出后继续修正" not in combined_source
    assert "发布前检查有警告，建议保存后继续修正" not in combined_source


def test_template_controller_writes_package_directory_and_cleans_failed_partial_write(tmp_path):
    package_dir = tmp_path / "package"
    files = {
        "README.md": "readme",
        "metadata.json": "{}\n",
    }

    def make_directory(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=False)

    def write_text_file(path: str, text: str) -> None:
        if path.endswith("README.md"):
            Path(path).write_text(text, encoding="utf-8")
            return
        raise OSError("disk full")

    error = TemplateSettingsController.write_template_package_directory(
        package_dir,
        files,
        make_directory=make_directory,
        write_text_file=write_text_file,
    )

    assert isinstance(error, OSError)
    assert str(error) == "disk full"
    assert not package_dir.exists()


def test_template_controller_preserves_write_error_when_partial_cleanup_fails(tmp_path, monkeypatch):
    package_dir = tmp_path / "package"
    files = {
        "README.md": "readme",
        "metadata.json": "{}\n",
    }

    def make_directory(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=False)

    def write_text_file(path: str, text: str) -> None:
        if path.endswith("README.md"):
            Path(path).write_text(text, encoding="utf-8")
            return
        raise OSError("disk full")

    original_unlink = Path.unlink

    def failing_unlink(path: Path, *args, **kwargs) -> None:
        if path.name == "README.md":
            raise PermissionError("file locked")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", failing_unlink)

    error = TemplateSettingsController.write_template_package_directory(
        package_dir,
        files,
        make_directory=make_directory,
        write_text_file=write_text_file,
    )

    assert isinstance(error, OSError)
    assert str(error) == "disk full"


def test_template_controller_writes_library_package_and_removes_new_empty_root_on_failure(tmp_path):
    library_root = tmp_path / "packages"
    package_dir = library_root / "package"
    files = {
        "README.md": "readme",
        "metadata.json": "{}\n",
    }

    def make_directory(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=False)

    def write_text_file(path: str, text: str) -> None:
        if path.endswith("README.md"):
            Path(path).write_text(text, encoding="utf-8")
            return
        raise OSError("disk full")

    error = TemplateSettingsController.write_template_package_directory(
        package_dir,
        files,
        make_directory=make_directory,
        write_text_file=write_text_file,
        root_dir=library_root,
    )

    assert isinstance(error, OSError)
    assert str(error) == "disk full"
    assert not package_dir.exists()
    assert not library_root.exists()


def test_settings_window_template_package_writers_delegate_directory_io_to_controller():
    window_path = Path(__file__).resolve().parents[1] / "ui" / "settings_ui" / "window.py"
    source = window_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    settings_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SettingsWindow")

    def method_source(name: str) -> str:
        method = next(
            node
            for node in settings_class.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        )
        return ast.get_source_segment(source, method) or ""

    for method_name in ["_export_template_release_package", "_save_template_to_library"]:
        body = method_source(method_name)
        assert "self.template_package_workflow.write(" in body
        assert "TemplateSettingsController.write_template_package_directory(" not in body
        assert "for relative_path, text in files.items()" not in body
        assert "child.unlink" not in body
        assert "created_dir" not in body
