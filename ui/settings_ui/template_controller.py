from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from core.messaging.template_output_validator import validate_template_output


@dataclass(frozen=True)
class TemplateSaveResult:
    saved: bool
    preflight_level: str
    preflight_message: str
    status_message: str
    is_error: bool


class TemplateSaveWorkflow:
    def run(
        self,
        *,
        preflight: Callable[[], tuple[str, str]],
        save: Callable[[], object],
        saved_status: Callable[[], tuple[str, bool]],
    ) -> TemplateSaveResult:
        level, preflight_message = preflight()
        if level == "error":
            return TemplateSaveResult(
                saved=False,
                preflight_level=level,
                preflight_message=preflight_message,
                status_message=f"保存已取消：发布前检查未通过。\n{preflight_message}",
                is_error=True,
            )
        save()
        status_message, is_error = saved_status()
        if level == "warning":
            status_message = f"{status_message}\n角色模板发布前检查有警告，建议查看发布前检查。"
        return TemplateSaveResult(
            saved=True,
            preflight_level=level,
            preflight_message=preflight_message,
            status_message=status_message,
            is_error=is_error,
        )


class TemplateReleaseArtifactWorkflow:
    def __init__(self, *, now: Callable[[], datetime] = datetime.now):
        self._now = now

    def build(
        self,
        *,
        character_name: str,
        character_setting: str,
        emotion_tags: str,
        sample_output: str,
        preflight_level: str,
        preflight_report: str,
        handoff_report: str,
    ) -> tuple[str, str, dict, dict[str, str]]:
        exported_at = self._now()
        _, draft = TemplateSettingsController.build_template_publish_draft_markdown(
            character_name=character_name,
            character_setting=character_setting,
            emotion_tags=emotion_tags,
            sample_output=sample_output,
            preflight=(preflight_level, preflight_report),
            handoff_report=handoff_report,
            generated_at=exported_at.strftime("%Y-%m-%d %H:%M:%S"),
        )
        metadata = TemplateSettingsController.build_template_release_package_metadata(
            character_name=character_name,
            character_setting=character_setting,
            emotion_tags=emotion_tags,
            sample_output=sample_output,
            preflight_level=preflight_level,
            exported_at=exported_at.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        level, files = TemplateSettingsController.build_template_release_package_files(
            metadata=metadata,
            draft=draft,
            preflight_report=preflight_report,
            character_name=character_name,
            character_setting=character_setting,
            emotion_tags=emotion_tags,
            sample_output_raw=sample_output,
        )
        return level, draft, metadata, files


@dataclass(frozen=True)
class TemplatePublishDraftWriteResult:
    message: str
    error: OSError | None = None


class TemplatePublishDraftWorkflow:
    def __init__(self, *, write_text_file: Callable[[str | Path, str], None] | None = None):
        self._write_text_file = write_text_file or (
            lambda path, text: Path(path).write_text(text, encoding="utf-8")
        )

    def write(self, *, path: str | Path, markdown: str, level: str) -> TemplatePublishDraftWriteResult:
        try:
            self._write_text_file(path, markdown)
        except OSError as error:
            return TemplatePublishDraftWriteResult(
                message=f"导出发布草稿失败：{error}",
                error=error,
            )
        message = f"已导出发布草稿：{path}"
        if level == "warning":
            message = f"{message}\n发布前检查有警告，建议导出后继续修正。"
        return TemplatePublishDraftWriteResult(message=message)


@dataclass(frozen=True)
class TemplatePackageWriteResult:
    package_dir: Path
    message: str
    error: OSError | None = None


class TemplatePackageWorkflow:
    def __init__(
        self,
        *,
        make_directory: Callable[[Path], None] | None = None,
        write_text_file: Callable[[str | Path, str], None] | None = None,
    ):
        self._make_directory = make_directory or (
            lambda path: path.mkdir(parents=True, exist_ok=False)
        )
        self._write_text_file = write_text_file or (
            lambda path, text: Path(path).write_text(text, encoding="utf-8")
        )

    def write(
        self,
        *,
        action: str,
        root: Path,
        package_name: str,
        files: dict[str, str],
        level: str,
    ) -> TemplatePackageWriteResult:
        package_dir = root / package_name
        error = TemplateSettingsController.write_template_package_directory(
            package_dir,
            files,
            make_directory=self._make_directory,
            write_text_file=self._write_text_file,
            root_dir=root if action == "library" else None,
        )
        if error:
            return TemplatePackageWriteResult(
                package_dir=package_dir,
                message=TemplateSettingsController.template_package_write_error_message(
                    action=action,
                    error=error,
                    package_dir=package_dir,
                ),
                error=error,
            )
        return TemplatePackageWriteResult(
            package_dir=package_dir,
            message=TemplateSettingsController.template_package_write_success_message(
                action=action,
                package_dir=package_dir,
                level=level,
            ),
        )


@dataclass(frozen=True)
class TemplateImportCompletion:
    validation_message: str
    status_message: str


@dataclass(frozen=True)
class TemplateLibraryViewState:
    rows: list[str]
    result_summary: str
    detail_text: str
    import_enabled: bool


class TemplateLibraryWorkflow:
    def __init__(
        self,
        root: Callable[[], Path],
        scan: Callable[[Path], list],
        *,
        ensure_directory: Callable[[Path], None] | None = None,
        open_directory: Callable[[Path], None] | None = None,
    ):
        self._root = root
        self._scan = scan
        self._ensure_directory = ensure_directory
        self._open_directory = open_directory
        self.visible_summaries: list = []

    def open_library_directory(self) -> Path:
        root = self._root()
        if self._ensure_directory is not None:
            self._ensure_directory(root)
        if self._open_directory is not None:
            self._open_directory(root)
        return root

    def refresh(
        self,
        *,
        search_text: str = "",
        filter_text: str = "全部",
        sort_text: str = "按时间（新到旧）",
        preflight_filter_text: str = "全部",
        time_filter_text: str = "全部",
    ) -> TemplateLibraryViewState:
        self.visible_summaries = TemplateSettingsController.filtered_template_library_summaries(
            self._scan(self._root()),
            search_text=search_text,
            filter_text=filter_text,
            sort_text=sort_text,
            preflight_filter_text=preflight_filter_text,
            time_filter_text=time_filter_text,
        )
        detail_text, import_enabled = TemplateSettingsController.template_library_selection_state(
            self.visible_summaries,
            0,
        )
        if not self.visible_summaries:
            detail_text = TemplateSettingsController.template_library_empty_detail_text(search_text)
        return TemplateLibraryViewState(
            rows=[TemplateSettingsController.template_library_row_text(summary) for summary in self.visible_summaries],
            result_summary=TemplateSettingsController.template_library_result_summary_text(
                self.visible_summaries,
                search_text=search_text,
                filter_text=filter_text,
                preflight_filter_text=preflight_filter_text,
                time_filter_text=time_filter_text,
            ),
            detail_text=detail_text,
            import_enabled=import_enabled,
        )

    def selection_state(self, row: int) -> tuple[str, bool]:
        return TemplateSettingsController.template_library_selection_state(self.visible_summaries, row)

    def import_selection(self, row: int) -> tuple[object | None, str | None]:
        return TemplateSettingsController.template_library_import_selection(self.visible_summaries, row)

    def load_import_selection(
        self,
        row: int,
        load_import_data: Callable[[Path], object],
    ) -> tuple[object | None, str | None]:
        summary, error = self.import_selection(row)
        if error:
            return None, error
        return load_import_data(summary.path), None

    def complete_import(
        self,
        editor,
        import_data,
        *,
        validate: Callable[[], str],
    ) -> TemplateImportCompletion:
        TemplateSettingsController.apply_template_import_data_to_editor(editor, import_data)
        validation_message = validate()
        return TemplateImportCompletion(
            validation_message=validation_message,
            status_message=TemplateSettingsController.template_import_status_message(
                import_data.character_name,
                validation_message,
            ),
        )


class TemplateSettingsController:
    """Extracted template-authoring helpers for SettingsWindow."""

    @staticmethod
    def safe_template_draft_filename(character_name: str) -> str:
        safe = "".join(ch for ch in character_name.strip() if ch.isalnum() or ch in ("-", "_"))
        return f"{safe or 'template'}-publish-draft.md"

    @staticmethod
    def make_template_release_package_dir_name(
        character_name: str,
        *,
        now: Callable[[], datetime] = datetime.now,
    ) -> str:
        safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in character_name.strip())
        safe = "-".join(part for part in safe.split("-") if part)
        timestamp = now().strftime("%Y-%m-%d-%H%M%S")
        if safe:
            return f"{safe}-template-package-{timestamp}"
        return f"template-package-{timestamp}"

    @staticmethod
    def template_sample_token_coverage(sample_output: str) -> str:
        found = set()
        for raw_line in sample_output.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            character_name = str(payload.get("character_name", "")).strip()
            if character_name in {"NARR", "CHOICE", "STAT", "CG"}:
                found.add(character_name)
        ordered = [token for token in ["NARR", "CHOICE", "STAT", "CG"] if token in found]
        return "、".join(ordered) if ordered else "无"

    @classmethod
    def template_sample_token_coverage_list(cls, sample_output: str) -> list[str]:
        coverage = cls.template_sample_token_coverage(sample_output)
        if coverage == "无":
            return []
        return [token for token in ["NARR", "CHOICE", "STAT", "CG"] if token in coverage.split("、")]

    @staticmethod
    def template_validation_result_message(sample_output: str) -> tuple[str, str]:
        if not sample_output.strip():
            return "error", "请先粘贴一段示例输出。"

        result = validate_template_output(sample_output)

        if result.errors:
            lines = ["示例输出有错误："]
            lines.extend(f"第 {issue.line} 行：{issue.message}" for issue in result.errors)
            if result.warnings:
                lines.append("警告：")
                lines.extend(f"第 {issue.line} 行：{issue.message}" for issue in result.warnings)
            return "error", "\n".join(lines)

        if result.warnings:
            lines = ["示例输出可用，但有警告："]
            lines.extend(f"第 {issue.line} 行：{issue.message}" for issue in result.warnings)
            return "warning", "\n".join(lines)

        return "ok", "示例输出校验通过。"

    @staticmethod
    def build_template_preflight_report(
        *,
        character_name: str,
        character_setting: str,
        emotion_tags: str,
        sample_output: str,
        require_sample_output: bool = True,
    ) -> tuple[str, str]:
        character_name = character_name.strip()
        character_setting = character_setting.strip()
        emotion_tags = emotion_tags.strip()

        errors = []
        warnings = []

        if not character_name:
            errors.append("角色名称不能为空")

        if not character_setting:
            warnings.append("角色设定为空，建议补充角色性格、称呼方式和对话边界。")
        elif len(character_setting) < 12:
            warnings.append("角色设定较短，建议补充角色性格、称呼方式和对话边界。")

        if not emotion_tags:
            warnings.append("情绪标签为空，角色可能只能使用默认立绘状态。")

        if not sample_output.strip():
            sample_line_count = 0
            if require_sample_output:
                errors.append("请先点击“填入示例”或粘贴 JSON-lines 示例输出")
            else:
                warnings.append(
                    "示例输出为空；保存配置不会保存示例输出，发布前建议点击“填入示例”或粘贴 JSON-lines 后再检查。"
                )
        else:
            sample_line_count = sum(1 for line in sample_output.splitlines() if line.strip())
            validation = validate_template_output(sample_output)
            errors.extend(f"第 {issue.line} 行：{issue.message}" for issue in validation.errors)
            warnings.extend(f"第 {issue.line} 行：{issue.message}" for issue in validation.warnings)

        name_for_report = character_name or "未填写"
        fix_suggestions = TemplateSettingsController.template_preflight_fix_suggestions(errors, warnings)
        lines = []
        if errors:
            lines.append("发布前检查未通过：")
            lines.append(f"角色名称：{name_for_report}")
            lines.append(f"示例输出：{sample_line_count} 行")
            lines.append("错误：")
            lines.extend(f"- {error}" for error in errors)
            if warnings:
                lines.append("警告：")
                lines.extend(f"- {warning}" for warning in warnings)
            if fix_suggestions:
                lines.append("修复建议：")
                lines.extend(f"- {suggestion}" for suggestion in fix_suggestions)
            return "error", "\n".join(lines)

        if warnings:
            lines.append("发布前检查可用，但有警告：")
            lines.append(f"角色名称：{name_for_report}")
            lines.append(f"示例输出：{sample_line_count} 行")
            lines.append("警告：")
            lines.extend(f"- {warning}" for warning in warnings)
            if fix_suggestions:
                lines.append("修复建议：")
                lines.extend(f"- {suggestion}" for suggestion in fix_suggestions)
            return "warning", "\n".join(lines)

        lines.append("发布前检查通过。")
        lines.append(f"角色名称：{name_for_report}")
        lines.append(f"示例输出：{sample_line_count} 行")
        lines.append("未发现错误或警告。")
        lines.append("建议继续生成发布清单或导出发布包。")
        lines.append('如需写入角色配置，请记得点击“保存配置”。')
        return "ok", "\n".join(lines)

    @classmethod
    def build_template_publish_handoff_report(
        cls,
        *,
        character_name: str,
        character_setting: str,
        emotion_tags: str,
        sample_output: str,
        preflight: tuple[str, str] | None = None,
        preflight_level: str | None = None,
        preflight_message: str | None = None,
    ) -> tuple[str, str]:
        if preflight is not None:
            preflight_level, preflight_message = preflight
        if preflight_level is None or preflight_message is None:
            raise TypeError("preflight tuple is required")

        character_name = character_name.strip() or "未填写"
        character_setting = character_setting.strip()
        emotion_tags = emotion_tags.strip()

        emotion_tag_count = sum(1 for line in emotion_tags.splitlines() if line.strip())
        sample_line_count = sum(1 for line in sample_output.splitlines() if line.strip())
        preflight_status = {
            "ok": "通过",
            "warning": "有警告",
            "error": "未通过",
        }.get(preflight_level, "未知")

        lines = [
            "角色模板发布清单：",
            f"角色名称：{character_name}",
            f"角色设定：{len(character_setting)} 字",
            f"情绪标签：{emotion_tag_count} 行",
            f"示例输出：{sample_line_count} 行",
            f"控制 token 覆盖：{cls.template_sample_token_coverage(sample_output)}",
            f"发布前检查：{preflight_status}",
            "边界：这是轻量交接清单，不是完整模板市场、多示例管理或正式发布工作流。",
            "发布前检查摘要：",
            preflight_message,
        ]
        return preflight_level, "\n".join(lines)

    @classmethod
    def build_template_publish_draft_markdown(
        cls,
        *,
        character_name: str,
        character_setting: str,
        emotion_tags: str,
        sample_output: str,
        preflight: tuple[str, str],
        handoff_report: str,
        generated_at: str,
    ) -> tuple[str, str]:
        preflight_level, preflight_message = preflight
        character_name = character_name.strip() or "未填写"
        character_setting = character_setting.strip()
        emotion_tags = emotion_tags.strip()
        sample_output = sample_output.strip()
        emotion_tag_count = sum(1 for line in emotion_tags.splitlines() if line.strip())
        sample_line_count = sum(1 for line in sample_output.splitlines() if line.strip())
        token_coverage = cls.template_sample_token_coverage(sample_output)
        preflight_status = {
            "ok": "通过",
            "warning": "有警告",
            "error": "未通过",
        }.get(preflight_level, "未知")

        markdown = "\n".join([
            f"# 角色模板发布草稿：{character_name}",
            "",
            f"生成时间：{generated_at}",
            "",
            "## 角色信息",
            "",
            f"- 角色名称：{character_name}",
            f"- 角色设定长度：{len(character_setting)} 字",
            f"- 情绪标签行数：{emotion_tag_count} 行",
            f"- 示例输出行数：{sample_line_count} 行",
            f"- 控制 token 覆盖：{token_coverage}",
            f"- 发布前检查：{preflight_status}",
            "",
            "## 角色设定",
            "",
            character_setting or "（空）",
            "",
            "## 情绪标签",
            "",
            "```text",
            emotion_tags,
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
            preflight_message,
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
        return preflight_level, markdown

    @classmethod
    def build_template_release_package_metadata(
        cls,
        *,
        character_name: str,
        character_setting: str,
        emotion_tags: str,
        sample_output: str,
        preflight_level: str,
        exported_at: str,
    ) -> dict:
        character_name = character_name.strip() or "未填写"
        character_setting = character_setting.strip()
        emotion_tags = emotion_tags.strip()
        sample_output = sample_output.strip()
        preflight_status = {
            "ok": "通过",
            "warning": "有警告",
            "error": "未通过",
        }.get(preflight_level, "未知")
        return {
            "schema_version": 1,
            "package_type": "galgame_agent.character_template.release_package",
            "character_name": character_name,
            "exported_at": exported_at,
            "preflight_level": preflight_level,
            "preflight_status": preflight_status,
            "character_setting_length": len(character_setting),
            "emotion_tag_lines": sum(1 for line in emotion_tags.splitlines() if line.strip()),
            "sample_output_lines": sum(1 for line in sample_output.splitlines() if line.strip()),
            "token_coverage": cls.template_sample_token_coverage_list(sample_output),
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

    @classmethod
    def build_template_release_package_files(
        cls,
        *,
        metadata: dict,
        draft: str,
        preflight_report: str,
        character_name: str,
        character_setting: str,
        emotion_tags: str,
        sample_output_raw: str,
    ) -> tuple[str, dict[str, str]]:
        character_name = character_name.strip() or "未填写"
        character_setting = character_setting.strip()
        emotion_tags = emotion_tags.strip()
        sample_output = sample_output_raw.strip()
        readme = "\n".join([
            f"# 角色模板发布包：{character_name}",
            "",
            f"导出时间：{metadata['exported_at']}",
            f"发布前检查：{metadata['preflight_status']}",
            f"控制 token 覆盖：{cls.template_sample_token_coverage(sample_output)}",
            "",
            "这是本地轻量模板发布包，用于 reviewer/维护者复核和发布候选留档。",
            "它不是自动发布、模板市场、多示例管理、审核队列或正式发布工作流。",
            "",
            "## 文件说明",
            "",
            "- `README.md`：发布包说明和文件清单。",
            "- `角色模板发布草稿.md`：面向 reviewer 阅读的 Markdown 草稿。",
            "- `template-output.jsonl`：当前 JSON-lines 示例输出，可直接复制到校验器。",
            "- `preflight-report.txt`：发布前检查摘要、错误/警告和修复建议。",
            "- `metadata.json`：机器可读元数据，不包含私有 API 配置或聊天历史。",
            "- `template-data.json`：导入当前角色模板所需的机器可读字段，不包含私有 API 配置、聊天历史或本机服务配置。",
            "",
        ])
        package_sample_output = sample_output_raw
        if package_sample_output and not package_sample_output.endswith("\n"):
            package_sample_output = f"{package_sample_output}\n"
        template_data = {
            "schema_version": 1,
            "package_type": "galgame_agent.character_template.import_data",
            "character_name": character_name,
            "character_setting": character_setting,
            "emotion_tags": emotion_tags,
            "sample_output": package_sample_output,
        }
        return metadata["preflight_level"], {
            "README.md": readme,
            "角色模板发布草稿.md": draft,
            "template-output.jsonl": package_sample_output,
            "preflight-report.txt": preflight_report + "\n",
            "metadata.json": json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            "template-data.json": json.dumps(template_data, ensure_ascii=False, indent=2) + "\n",
        }

    @staticmethod
    def write_template_package_directory(
        package_dir: Path,
        files: dict[str, str],
        *,
        make_directory: Callable[[Path], None],
        write_text_file: Callable[[str, str], None],
        root_dir: Path | None = None,
    ) -> OSError | None:
        """Create and write a template package directory, cleaning partial writes on failure."""
        root_created = False
        dir_created = False
        try:
            if root_dir is not None and not root_dir.exists():
                make_directory(root_dir)
                root_created = True
            make_directory(package_dir)
            dir_created = True
            for relative_path, text in files.items():
                write_text_file(str(package_dir / relative_path), text)
        except OSError as exc:
            if dir_created:
                for child in package_dir.iterdir() if package_dir.exists() else []:
                    if child.is_file():
                        try:
                            child.unlink(missing_ok=True)
                        except OSError:
                            pass
                try:
                    package_dir.rmdir()
                except OSError:
                    pass
            if root_created and root_dir is not None and root_dir.exists() and not any(root_dir.iterdir()):
                try:
                    root_dir.rmdir()
                except OSError:
                    pass
            return exc
        return None

    @staticmethod
    def filtered_template_library_summaries(
        summaries: list,
        *,
        search_text: str = "",
        filter_text: str = "全部",
        sort_text: str = "按时间（新到旧）",
        preflight_filter_text: str = "全部",
        time_filter_text: str = "全部",
        now: Callable[[], datetime] = datetime.now,
    ) -> list:
        search_text = search_text.strip()
        if search_text:
            lowered = search_text.casefold()
            summaries = [summary for summary in summaries if lowered in summary.character_name.casefold()]
        if filter_text == "只看可导入":
            summaries = [summary for summary in summaries if summary.importable]
        elif filter_text == "只看不可导入":
            summaries = [summary for summary in summaries if not summary.importable]
        if preflight_filter_text == "只看通过":
            summaries = [summary for summary in summaries if summary.preflight_status == "通过"]
        elif preflight_filter_text == "只看有警告":
            summaries = [summary for summary in summaries if summary.preflight_status == "有警告"]
        if time_filter_text == "最近 1 天":
            cutoff = now() - timedelta(days=1)
            summaries = [
                summary
                for summary in summaries
                if TemplateSettingsController._is_exported_at_recent(summary.exported_at, cutoff)
            ]
        if sort_text == "按名称":
            return sorted(summaries, key=lambda summary: summary.character_name.casefold())
        return sorted(summaries, key=lambda summary: (summary.exported_at or "", summary.character_name.casefold()), reverse=True)

    @staticmethod
    def _is_exported_at_recent(exported_at: str, cutoff: datetime) -> bool:
        if not exported_at:
            return False
        try:
            return datetime.fromisoformat(exported_at) >= cutoff
        except ValueError:
            return False

    @staticmethod
    def template_import_status_message(character_name: str, validation_message: str) -> str:
        if "有警告" in validation_message:
            return (
                f"已导入模板：{character_name}。当前示例输出仍有警告，建议先修正后再保存配置或分享给 reviewer。\n"
                "如需继续交接，也可以生成发布清单或导出发布包。"
            )
        return (
            f"已导入模板：{character_name}。示例输出已自动重新校验，建议继续点击“保存配置”。\n"
            "如需交接，也可以继续生成发布清单或导出发布包。"
        )

    @staticmethod
    def template_library_import_confirmation_message() -> str:
        return (
            "导入选中模板会覆盖当前角色名称、角色设定、情绪标签和示例输出。\n"
            "导入后会自动重新校验示例输出，但不会自动保存配置。\n"
            "如果确认无误，请在导入后继续点击“保存配置”。\n\n是否继续？"
        )

    @staticmethod
    def apply_template_import_data_to_editor(editor, import_data) -> None:
        editor.char_name_edit.setText(import_data.character_name)
        editor.char_setting_edit.setPlainText(import_data.character_setting)
        editor.emotion_tags_edit.setPlainText(import_data.emotion_tags)
        editor.template_sample_output_edit.setPlainText(import_data.sample_output)

    @staticmethod
    def template_library_detail_text(summary) -> str:
        detail_lines = [
            f"角色名称：{summary.character_name}",
            f"导入状态：{'可导入' if summary.importable else '不可导入'}",
            f"发布前检查：{summary.preflight_status or '-'}",
            f"路径：{summary.path}",
        ]
        if summary.token_coverage:
            detail_lines.append(f"控制 token 覆盖：{'、'.join(summary.token_coverage)}")
        if summary.missing_files:
            detail_lines.append(f"缺失文件：{', '.join(summary.missing_files)}")
        if summary.reason:
            detail_lines.append(f"原因：{summary.reason}")
        if summary.importable:
            detail_lines.append("下一步建议：可直接导入到当前编辑区，并在保存前重新确认配置。")
        else:
            detail_lines.append("下一步建议：先补齐缺失文件或重新导出发布包，再回来刷新模板库。")
        return "\n".join(detail_lines)

    @classmethod
    def template_library_selection_state(cls, summaries: list, row: int) -> tuple[str, bool]:
        if row < 0 or row >= len(summaries):
            return "暂无本地模板。", False
        summary = summaries[row]
        return cls.template_library_detail_text(summary), bool(summary.importable)

    @staticmethod
    def template_library_import_selection(summaries: list, row: int) -> tuple[object | None, str | None]:
        if row < 0 or row >= len(summaries):
            return None, "请先选择一个可导入模板。"
        summary = summaries[row]
        if not summary.importable:
            return None, "请先选择一个可导入模板。"
        return summary, None

    @staticmethod
    def template_library_result_summary_text(
        summaries: list,
        *,
        search_text: str = "",
        filter_text: str = "全部",
        preflight_filter_text: str = "全部",
        time_filter_text: str = "全部",
    ) -> str:
        total = len(summaries)
        importable = sum(1 for summary in summaries if summary.importable)
        blocked = total - importable
        is_filtered = search_text or filter_text != "全部" or preflight_filter_text != "全部" or time_filter_text != "全部"
        if is_filtered:
            if total == 0:
                return "当前筛选结果：0 个模板"
            if importable == total:
                return f"当前筛选结果：{total} 个模板（可导入 {importable} 个）"
            if blocked == total:
                return f"当前筛选结果：{total} 个模板（不可导入 {blocked} 个）"
            return f"当前筛选结果：{total} 个模板（可导入 {importable} 个，不可导入 {blocked} 个）"
        return f"共 {total} 个模板：{importable} 个可导入，{blocked} 个不可导入"

    @staticmethod
    def template_library_row_text(summary) -> str:
        if getattr(summary, "is_valid", False) and getattr(summary, "importable", False):
            coverage = "/".join(getattr(summary, "token_coverage", ()) or ()) or "no-tokens"
            exported_at = getattr(summary, "exported_at", "") or "unknown-time"
            return f"{summary.character_name}｜可导入｜{summary.preflight_status}｜{coverage}｜{exported_at}"
        reason = getattr(summary, "reason", "") or "不可导入"
        return f"{summary.character_name}｜不可导入｜{reason}"

    @staticmethod
    def template_library_empty_detail_text(search_text: str = "") -> str:
        if search_text.strip():
            return "没有匹配的本地模板。\n下一步建议：调整搜索关键词，或清空搜索后重新选择模板。"
        return "暂无本地模板。\n下一步建议：先保存到模板库，或打开模板库目录检查是否有可用发布包。"

    @staticmethod
    def template_package_write_success_message(*, action: str, package_dir: Path, level: str) -> str:
        if action == "library":
            message = f"已保存到模板库：{package_dir}"
            if level == "warning":
                return f"{message}\n发布前检查有警告，建议保存后继续修正。"
            return message

        message = f"已导出发布包：{package_dir}"
        if level == "warning":
            return f"{message}\n发布前检查有警告，建议导出后继续修正。"
        return message

    @staticmethod
    def template_package_write_error_message(*, action: str, error: OSError, package_dir: Path) -> str:
        if action == "library":
            return f"保存到模板库失败：{error}\n目标路径：{package_dir}"
        return f"导出发布包失败：{error}\n目标路径：{package_dir}"

    @staticmethod
    def build_template_sample_output(character_name: str, sample_type: str) -> str:
        character_name = character_name.strip() or "小雪"
        character_line = {
            "character_name": character_name,
            "speech": "你好，今天也一起努力吧。",
            "sprite": "0",
        }
        narr_line = {
            "character_name": "NARR",
            "speech": "微风吹过窗边，房间里泛起柔和的光。",
            "sprite": "-1",
        }
        choice_line = {
            "character_name": "CHOICE",
            "speech": "继续聊天/看看窗外/暂时离开",
            "sprite": "-1",
        }
        branch_narr_line = {
            "character_name": "NARR",
            "speech": "走廊尽头传来轻微脚步声，新的分岔点出现了。",
            "sprite": "-1",
        }
        branch_character_line = {
            "character_name": character_name,
            "speech": "这里可能藏着关键线索，我们要怎么行动？",
            "sprite": "0",
        }
        branch_stat_line = {
            "character_name": "STAT",
            "speech": "好感度 +1；线索：旧钥匙已发现",
            "sprite": "-1",
        }
        branch_choice_line = {
            "character_name": "CHOICE",
            "speech": "调查走廊/询问同伴/先回教室",
            "sprite": "-1",
        }
        library_review_narr_line = {
            "character_name": "NARR",
            "speech": "你从本地模板库中选中一个模板包，准备复查它是否适合当前剧情。",
            "sprite": "-1",
        }
        library_review_character_line = {
            "character_name": character_name,
            "speech": "在正式导入之前，我想先把这个模板复核一遍，确认台词语气和控制 token 都合适。",
            "sprite": "0",
        }
        library_review_stat_line = {
            "character_name": "STAT",
            "speech": "模板包复核完成；建议：导入后重新检查并保存配置。",
            "sprite": "-1",
        }
        library_review_choice_line = {
            "character_name": "CHOICE",
            "speech": "直接导入模板/先查看发布清单/继续调整当前模板",
            "sprite": "-1",
        }
        library_repair_narr_line = {
            "character_name": "NARR",
            "speech": "你注意到模板复查结果里还有警告，决定先整理修复顺序。",
            "sprite": "-1",
        }
        library_repair_character_line = {
            "character_name": character_name,
            "speech": "我会先把容易修正的字段补齐，再重新检查一次，确认警告有没有减少。",
            "sprite": "0",
        }
        library_repair_stat_line = {
            "character_name": "STAT",
            "speech": "模板修正建议：先补齐情绪标签与角色设定，再复查并决定是否保存配置。",
            "sprite": "-1",
        }
        library_repair_choice_line = {
            "character_name": "CHOICE",
            "speech": "先补角色设定/先补情绪标签/重新检查当前模板",
            "sprite": "-1",
        }
        emotion_happy_line = {
            "character_name": character_name,
            "speech": "听到这个消息，我也忍不住笑了起来。",
            "sprite": "1",
        }
        emotion_serious_line = {
            "character_name": character_name,
            "speech": "不过接下来要认真一点，我有些担心前面的情况。",
            "sprite": "2",
        }
        emotion_narr_line = {
            "character_name": "NARR",
            "speech": "她的表情从放松变得明亮，又逐渐认真起来。",
            "sprite": "-1",
        }
        stat_line = {
            "character_name": "STAT",
            "speech": "好感度 +1",
            "sprite": "-1",
        }
        cg_line = {
            "character_name": "CG",
            "speech": "夕阳下的教室，柔和光线，动漫风格，高质量",
            "sprite": "-1",
        }

        if sample_type == "基础对话":
            sample_lines = [character_line, narr_line, choice_line]
        elif sample_type == "情绪切换示例":
            sample_lines = [character_line, emotion_happy_line, emotion_serious_line, emotion_narr_line]
        elif sample_type == "CG 示例":
            sample_lines = [character_line, cg_line, choice_line]
        elif sample_type == "剧情分支示例":
            sample_lines = [branch_narr_line, branch_character_line, branch_stat_line, branch_choice_line]
        elif sample_type == "模板复用示例":
            sample_lines = [
                library_review_narr_line,
                library_review_character_line,
                library_review_stat_line,
                library_review_choice_line,
            ]
        elif sample_type == "模板修正示例":
            sample_lines = [
                library_repair_narr_line,
                library_repair_character_line,
                library_repair_stat_line,
                library_repair_choice_line,
            ]
        else:
            sample_lines = [character_line, narr_line, choice_line, stat_line, cg_line]

        return "\n".join(json.dumps(line, ensure_ascii=False) for line in sample_lines)

    @staticmethod
    def template_preflight_fix_suggestions(errors: list[str], warnings: list[str]) -> list[str]:
        suggestions = []

        def add_suggestion(suggestion: str):
            if suggestion not in suggestions:
                suggestions.append(suggestion)

        for issue in [*errors, *warnings]:
            if "角色名称不能为空" in issue:
                add_suggestion("填写角色名称，例如：诺艾尔。")
            if "请先点击“填入示例”" in issue or "缺少示例输出" in issue:
                add_suggestion("点击“填入示例”生成一份可用 JSON-lines 后再修改。")
            if "缺少必填字段" in issue and "sprite" in issue:
                add_suggestion('补齐对应 JSON 对象的必填字段，例如 sprite；如果不切换立绘可填 "-1"。')
                add_suggestion("点击“填入示例”生成一份可用 JSON-lines 后再修改。")
            if "角色设定为空" in issue or "角色设定较短" in issue:
                add_suggestion("补充角色性格、称呼方式和对话边界，方便模型稳定保持人设。")
            if "情绪标签为空" in issue:
                add_suggestion("补充情绪标签，例如：0: neutral、1: happy。")
            if "CG 的 prompt 应放在 speech" in issue:
                add_suggestion('把 CG prompt 放到 speech，并将 sprite 设为 "-1"。')

        if errors:
            add_suggestion("优先先修错误，再回头处理警告。")
            add_suggestion('重新点击“发布前检查”确认状态是否变为“通过”或“有警告”。')
        if warnings and not errors:
            add_suggestion("如果暂时不修，也建议在分享给 reviewer 前至少再复查一次。")
            add_suggestion('重新点击“发布前检查”确认警告是否减少。')

        return suggestions
