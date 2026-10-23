from pathlib import Path

from core.templates.template_package import load_template_import_data, scan_template_packages


REQUIRED_PACKAGE_FILES = {
    "README.md",
    "角色模板发布草稿.md",
    "template-output.jsonl",
    "preflight-report.txt",
    "metadata.json",
}


def _write_release_package_metadata(
    package_dir: Path,
    *,
    character_name: str = "诺艾尔",
    schema_version: int = 1,
    package_type: str = "galgame_agent.character_template.release_package",
    files: list[str] | None = None,
    boundaries: dict[str, bool] | None = None,
) -> None:
    files = files or sorted(REQUIRED_PACKAGE_FILES)
    boundaries = boundaries or {
        "local_only": True,
        "contains_private_api_config": False,
        "contains_chat_history": False,
        "is_marketplace_publish": False,
    }
    (package_dir / "metadata.json").write_text(
        "\n".join(
            [
                "{",
                f'  "schema_version": {schema_version},',
                f'  "package_type": "{package_type}",',
                f'  "character_name": "{character_name}",',
                '  "exported_at": "2026-06-13T12:00:00",',
                '  "preflight_level": "ok",',
                '  "preflight_status": "通过",',
                '  "token_coverage": ["NARR", "CHOICE"],',
                f'  "files": {__import__("json").dumps(files, ensure_ascii=False)},',
                f'  "boundaries": {__import__("json").dumps(boundaries, ensure_ascii=False)}',
                "}",
            ]
        ),
        encoding="utf-8",
    )


def _write_required_package_files(package_dir: Path) -> None:
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


def _write_template_data(package_dir: Path) -> None:
    (package_dir / "template-data.json").write_text(
        '{"schema_version":1,"package_type":"galgame_agent.character_template.import_data","character_name":"诺艾尔","character_setting":"认真可靠的见习骑士。","emotion_tags":"0: neutral\\n1: happy","sample_output":"{\\"character_name\\":\\"诺艾尔\\",\\"speech\\":\\"你好\\",\\"sprite\\":\\"0\\"}\\n"}',
        encoding="utf-8",
    )


def test_scan_template_packages_returns_empty_for_missing_library(tmp_path: Path) -> None:
    result = scan_template_packages(tmp_path / "missing-library")
    assert result == []


def test_scan_template_packages_reports_missing_metadata(tmp_path: Path) -> None:
    package_dir = tmp_path / "broken-package"
    package_dir.mkdir()

    summaries = scan_template_packages(tmp_path)

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.is_valid is False
    assert summary.importable is False
    assert "metadata.json" in summary.reason


def test_load_template_import_data_reads_template_data_json(tmp_path: Path) -> None:
    package_dir = tmp_path / "valid-package"
    package_dir.mkdir()
    _write_template_data(package_dir)

    data = load_template_import_data(package_dir)

    assert data.character_name == "诺艾尔"
    assert data.character_setting == "认真可靠的见习骑士。"
    assert data.emotion_tags == "0: neutral\n1: happy"
    assert data.sample_output.endswith("\n")


def test_scan_template_packages_reports_malformed_metadata_json(tmp_path: Path) -> None:
    package_dir = tmp_path / "malformed-package"
    package_dir.mkdir()
    (package_dir / "metadata.json").write_text("{not-json", encoding="utf-8")

    summary = scan_template_packages(tmp_path)[0]

    assert summary.is_valid is False
    assert summary.importable is False
    assert "cannot parse" in summary.reason


def test_scan_template_packages_rejects_unsupported_package_type(tmp_path: Path) -> None:
    package_dir = tmp_path / "unsupported-type"
    package_dir.mkdir()
    _write_required_package_files(package_dir)
    _write_release_package_metadata(
        package_dir,
        package_type="galgame_agent.character_template.other_package",
    )

    summary = scan_template_packages(tmp_path)[0]

    assert summary.is_valid is False
    assert summary.importable is False
    assert "unsupported package type" in summary.reason


def test_scan_template_packages_reports_missing_required_files(tmp_path: Path) -> None:
    package_dir = tmp_path / "missing-files"
    package_dir.mkdir()
    (package_dir / "README.md").write_text("# package\n", encoding="utf-8")
    _write_release_package_metadata(package_dir)

    summary = scan_template_packages(tmp_path)[0]

    assert summary.is_valid is False
    assert summary.importable is False
    assert "template-output.jsonl" in summary.missing_files
    assert "preflight-report.txt" in summary.missing_files


def test_scan_template_packages_reports_privacy_boundary_failure(tmp_path: Path) -> None:
    package_dir = tmp_path / "privacy-failure"
    package_dir.mkdir()
    _write_required_package_files(package_dir)
    _write_release_package_metadata(
        package_dir,
        boundaries={
            "local_only": True,
            "contains_private_api_config": True,
            "contains_chat_history": False,
            "is_marketplace_publish": False,
        },
    )

    summary = scan_template_packages(tmp_path)[0]

    assert summary.is_valid is False
    assert summary.importable is False
    assert "privacy boundary" in summary.reason


def test_scan_template_packages_reads_valid_package_summary(tmp_path: Path) -> None:
    package_dir = tmp_path / "valid-package"
    package_dir.mkdir()
    _write_required_package_files(package_dir)
    _write_release_package_metadata(package_dir)
    _write_template_data(package_dir)

    summary = scan_template_packages(tmp_path)[0]

    assert summary.is_valid is True
    assert summary.importable is True
    assert summary.character_name == "诺艾尔"
    assert summary.exported_at == "2026-06-13T12:00:00"
    assert summary.preflight_level == "ok"
    assert summary.preflight_status == "通过"
    assert summary.token_coverage == ("NARR", "CHOICE")
    assert summary.missing_files == ()


def test_load_template_import_data_falls_back_to_markdown_for_old_package(tmp_path: Path) -> None:
    package_dir = tmp_path / "old-package"
    package_dir.mkdir()
    _write_required_package_files(package_dir)
    _write_release_package_metadata(package_dir)

    data = load_template_import_data(package_dir)

    assert data.character_name == "诺艾尔"
    assert data.character_setting == "认真可靠的见习骑士。"
    assert data.emotion_tags == "0: neutral\n1: happy"
    assert data.sample_output.endswith("\n")


def test_load_template_import_data_falls_back_to_markdown_when_template_data_is_broken(tmp_path: Path) -> None:
    package_dir = tmp_path / "broken-template-data"
    package_dir.mkdir()
    _write_required_package_files(package_dir)
    _write_release_package_metadata(package_dir)
    (package_dir / "template-data.json").write_text("{broken", encoding="utf-8")

    data = load_template_import_data(package_dir)

    assert data.character_name == "诺艾尔"
    assert data.sample_output.endswith("\n")
