from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


REQUIRED_PACKAGE_FILES = (
    "README.md",
    "角色模板发布草稿.md",
    "template-output.jsonl",
    "preflight-report.txt",
    "metadata.json",
)
RELEASE_PACKAGE_TYPE = "galgame_agent.character_template.release_package"
IMPORT_DATA_PACKAGE_TYPE = "galgame_agent.character_template.import_data"


@dataclass(frozen=True)
class TemplatePackageSummary:
    path: Path
    character_name: str
    exported_at: str
    preflight_level: str
    preflight_status: str
    token_coverage: tuple[str, ...]
    files_present: tuple[str, ...]
    missing_files: tuple[str, ...]
    is_valid: bool
    importable: bool
    reason: str


@dataclass(frozen=True)
class TemplateImportData:
    character_name: str
    character_setting: str
    emotion_tags: str
    sample_output: str


class TemplatePackageError(RuntimeError):
    pass


def scan_template_packages(root: Path) -> list[TemplatePackageSummary]:
    if not root.exists():
        return []

    summaries: list[TemplatePackageSummary] = []
    for package_dir in sorted((path for path in root.iterdir() if path.is_dir()), key=lambda path: path.name):
        summaries.append(_scan_package_dir(package_dir))
    return summaries


def load_template_import_data(package_dir: Path) -> TemplateImportData:
    template_data_path = package_dir / "template-data.json"
    if template_data_path.exists():
        try:
            payload = json.loads(template_data_path.read_text(encoding="utf-8"))
            if payload.get("package_type") != IMPORT_DATA_PACKAGE_TYPE:
                raise TemplatePackageError("unsupported import data package type")
            return TemplateImportData(
                character_name=payload["character_name"],
                character_setting=payload["character_setting"],
                emotion_tags=payload["emotion_tags"],
                sample_output=payload["sample_output"],
            )
        except (KeyError, TypeError, json.JSONDecodeError, TemplatePackageError):
            fallback = _load_template_import_data_from_markdown(package_dir)
            if fallback is not None:
                return fallback
            raise TemplatePackageError("no import data available")

    fallback = _load_template_import_data_from_markdown(package_dir)
    if fallback is not None:
        return fallback
    raise TemplatePackageError("no import data available")


def _scan_package_dir(package_dir: Path) -> TemplatePackageSummary:
    files_present = tuple(sorted(path.name for path in package_dir.iterdir()))
    metadata_path = package_dir / "metadata.json"
    if not metadata_path.exists():
        return TemplatePackageSummary(
            path=package_dir,
            character_name=package_dir.name,
            exported_at="",
            preflight_level="error",
            preflight_status="不可导入",
            token_coverage=(),
            files_present=files_present,
            missing_files=("metadata.json",),
            is_valid=False,
            importable=False,
            reason="missing metadata.json",
        )

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return TemplatePackageSummary(
            path=package_dir,
            character_name=package_dir.name,
            exported_at="",
            preflight_level="error",
            preflight_status="不可导入",
            token_coverage=(),
            files_present=files_present,
            missing_files=(),
            is_valid=False,
            importable=False,
            reason="cannot parse metadata.json",
        )

    if metadata.get("schema_version") != 1:
        return _invalid_summary(package_dir, files_present, metadata, "unsupported schema version")

    if metadata.get("package_type") != RELEASE_PACKAGE_TYPE:
        return _invalid_summary(package_dir, files_present, metadata, "unsupported package type")

    missing_files = tuple(
        file_name for file_name in REQUIRED_PACKAGE_FILES if not (package_dir / file_name).exists()
    )
    if missing_files:
        return TemplatePackageSummary(
            path=package_dir,
            character_name=metadata.get("character_name", package_dir.name),
            exported_at=metadata.get("exported_at", ""),
            preflight_level=metadata.get("preflight_level", "error"),
            preflight_status=metadata.get("preflight_status", "不可导入"),
            token_coverage=tuple(metadata.get("token_coverage", [])),
            files_present=files_present,
            missing_files=missing_files,
            is_valid=False,
            importable=False,
            reason="missing required files",
        )

    boundaries = metadata.get("boundaries", {})
    if (
        boundaries.get("contains_private_api_config") is True
        or boundaries.get("contains_chat_history") is True
        or boundaries.get("is_marketplace_publish") is True
    ):
        return _invalid_summary(package_dir, files_present, metadata, "privacy boundary failed")

    try:
        load_template_import_data(package_dir)
    except TemplatePackageError as exc:
        return TemplatePackageSummary(
            path=package_dir,
            character_name=metadata.get("character_name", package_dir.name),
            exported_at=metadata.get("exported_at", ""),
            preflight_level=metadata.get("preflight_level", "ok"),
            preflight_status=metadata.get("preflight_status", "通过"),
            token_coverage=tuple(metadata.get("token_coverage", [])),
            files_present=files_present,
            missing_files=(),
            is_valid=True,
            importable=False,
            reason=str(exc),
        )

    return TemplatePackageSummary(
        path=package_dir,
        character_name=metadata.get("character_name", package_dir.name),
        exported_at=metadata.get("exported_at", ""),
        preflight_level=metadata.get("preflight_level", "ok"),
        preflight_status=metadata.get("preflight_status", "通过"),
        token_coverage=tuple(metadata.get("token_coverage", [])),
        files_present=files_present,
        missing_files=(),
        is_valid=True,
        importable=True,
        reason="",
    )


def _invalid_summary(
    package_dir: Path,
    files_present: tuple[str, ...],
    metadata: dict,
    reason: str,
) -> TemplatePackageSummary:
    return TemplatePackageSummary(
        path=package_dir,
        character_name=metadata.get("character_name", package_dir.name),
        exported_at=metadata.get("exported_at", ""),
        preflight_level=metadata.get("preflight_level", "error"),
        preflight_status=metadata.get("preflight_status", "不可导入"),
        token_coverage=tuple(metadata.get("token_coverage", [])),
        files_present=files_present,
        missing_files=(),
        is_valid=False,
        importable=False,
        reason=reason,
    )


def _load_template_import_data_from_markdown(package_dir: Path) -> TemplateImportData | None:
    draft_path = package_dir / "角色模板发布草稿.md"
    if not draft_path.exists():
        return None

    content = draft_path.read_text(encoding="utf-8")
    character_name = _parse_markdown_title_name(content)
    character_setting = _parse_markdown_section_text(content, "## 角色设定")
    emotion_tags = _parse_markdown_fenced_block(content, "## 情绪标签", "text")
    sample_output = _parse_markdown_fenced_block(content, "## 示例输出 JSON-lines", "jsonl")

    if not all([character_name, character_setting, emotion_tags, sample_output]):
        return None

    if not sample_output.endswith("\n"):
        sample_output += "\n"

    return TemplateImportData(
        character_name=character_name,
        character_setting=character_setting,
        emotion_tags=emotion_tags,
        sample_output=sample_output,
    )


def _parse_markdown_title_name(content: str) -> str:
    match = re.search(r"^# 角色模板发布草稿：(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _parse_markdown_section_text(content: str, heading: str) -> str:
    pattern = rf"{re.escape(heading)}\n\n(.+?)(?:\n## |\Z)"
    match = re.search(pattern, content, re.DOTALL)
    return match.group(1).strip() if match else ""


def _parse_markdown_fenced_block(content: str, heading: str, fence_name: str) -> str:
    pattern = rf"{re.escape(heading)}\n```{re.escape(fence_name)}\n(.+?)\n```"
    match = re.search(pattern, content, re.DOTALL)
    return match.group(1) if match else ""
