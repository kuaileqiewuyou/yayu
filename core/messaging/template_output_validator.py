"""Lightweight validation for character template JSON-lines examples."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any


_ALLOWED_CONTROL_TOKENS = {"COT", "NARR", "CHOICE", "STAT", "SCENE", "BGM", "bgm", "CG", "CARD", "INFO"}
_REQUIRED_FIELDS = ("character_name", "speech", "sprite")


@dataclass(frozen=True)
class ValidationIssue:
    line: int
    message: str


@dataclass
class TemplateOutputValidationResult:
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors


def validate_template_output(text: str) -> TemplateOutputValidationResult:
    """Validate a JSON-lines character template output sample.

    Each non-empty line must be one JSON object containing the basic template
    fields. The validator is pure logic and intentionally lightweight so it can
    be used by docs, tests, or UI code without pulling in runtime dependencies.
    """

    result = TemplateOutputValidationResult()

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            result.errors.append(
                ValidationIssue(line_number, f"JSON 解析失败: {exc.msg}")
            )
            continue

        if not isinstance(payload, dict):
            result.errors.append(ValidationIssue(line_number, "每行必须是 JSON 对象"))
            continue

        _validate_object(payload, line_number, result)

    return result


def _validate_object(
    payload: dict[str, Any],
    line_number: int,
    result: TemplateOutputValidationResult,
) -> None:
    missing_fields = [field for field in _REQUIRED_FIELDS if field not in payload]
    if missing_fields:
        result.errors.append(
            ValidationIssue(line_number, f"缺少必填字段: {', '.join(missing_fields)}")
        )

    character_name = payload.get("character_name")
    if _is_blank(character_name):
        result.errors.append(ValidationIssue(line_number, "缺少必填字段: character_name"))
        return

    name = str(character_name)
    speech = payload.get("speech", "")
    sprite = payload.get("sprite", "")

    if name == "CHOICE":
        options = [option.strip() for option in str(speech).split("/") if option.strip()]
        if not 2 <= len(options) <= 4:
            result.errors.append(
                ValidationIssue(line_number, "CHOICE 的 speech 必须包含 2-4 个选项")
            )

    if name == "CG" and _is_blank(speech) and not _is_blank(sprite) and sprite != "-1" and sprite != -1:
        result.warnings.append(
            ValidationIssue(line_number, "CG 的 prompt 应放在 speech，不要放在 sprite")
        )

    if _looks_like_unknown_control_token(name):
        result.warnings.append(ValidationIssue(line_number, f"未知控制 token: {name}"))


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _looks_like_unknown_control_token(name: str) -> bool:
    return (
        name not in _ALLOWED_CONTROL_TOKENS
        and name.isascii()
        and name.isalpha()
        and name.upper() == name
    )
