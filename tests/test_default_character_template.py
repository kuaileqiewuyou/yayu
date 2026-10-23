from __future__ import annotations

import json
from pathlib import Path

from core.messaging.template_output_validator import validate_template_output


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "data" / "character_templates" / "default.txt"


def _read_default_template() -> str:
    return DEFAULT_TEMPLATE.read_text(encoding="utf-8")


def _example_json_lines(template_text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in template_text.splitlines():
        line = raw_line.strip()
        if line.startswith("{{") and line.endswith("}}"):
            # default.txt is itself a format template, so JSON examples are escaped.
            lines.append(line.replace("{{", "{").replace("}}", "}"))
    return lines


def _example_payloads(template_text: str) -> list[dict[str, str]]:
    return [json.loads(line.replace("{char_name}", "小春")) for line in _example_json_lines(template_text)]


def test_default_character_template_documents_cg_prompt_boundary() -> None:
    template_text = _read_default_template()

    assert "CG" in template_text
    assert "speech" in template_text and "prompt" in template_text
    assert "不要" in template_text and "prompt" in template_text and "sprite" in template_text


def test_default_character_template_documents_unknown_token_fallback() -> None:
    template_text = _read_default_template()

    assert "不确定" in template_text
    assert "token" in template_text
    assert "优先" in template_text
    assert "普通角色名" in template_text


def test_default_character_template_examples_cover_supported_roles_and_validate() -> None:
    template_text = _read_default_template()
    example_lines = _example_json_lines(template_text)
    payloads = _example_payloads(template_text)

    character_names = {payload["character_name"] for payload in payloads}
    assert "{char_name}" in {json.loads(line)["character_name"] for line in example_lines}
    assert {"NARR", "CHOICE", "STAT", "CG"}.issubset(character_names)

    cg_payloads = [payload for payload in payloads if payload["character_name"] == "CG"]
    assert cg_payloads
    for payload in cg_payloads:
        assert payload["speech"].strip()
        assert payload["sprite"] == "-1"

    validation_text = "\n".join(line.replace("{char_name}", "小春") for line in example_lines)
    result = validate_template_output(validation_text)
    assert result.errors == []
    assert result.warnings == []
