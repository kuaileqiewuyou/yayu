from pathlib import Path
import re


def test_gitignore_ignores_generated_cg_cache() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    gitignore_path = repo_root / ".gitignore"

    rules = [
        line.strip()
        for line in gitignore_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert "data/cg/" in rules


def test_manual_cg_preview_smoke_helper_is_documented() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    assert "docs/testing.md" in readme
    text = (repo_root / "docs" / "testing.md").read_text(encoding="utf-8")
    assert "scripts\\manual_cg_preview_smoke.py" in text or "scripts/manual_cg_preview_smoke.py" in text
    assert (repo_root / "scripts" / "manual_cg_preview_smoke.py").is_file()
    assert "manual-preview-smoke.png" in text
    assert any(
        phrase in text
        for phrase in [
            "不需要启动 LLM 或 ComfyUI",
            "不需要 ComfyUI",
            "不经过 ComfyUI",
            "without ComfyUI",
            "does not require ComfyUI",
        ]
    )


def test_character_template_control_tokens_user_guide_is_documented() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    guide_path = repo_root / "docs" / "user-guides" / "character-template-control-tokens.md"
    readme_path = repo_root / "README.md"
    default_template_path = repo_root / "data" / "character_templates" / "default.txt"

    guide_text = guide_path.read_text(encoding="utf-8")
    for required_text in [
        "character_name",
        "speech",
        "sprite",
        "CG",
        "STAT",
        "CHOICE",
        "ComfyUI",
        "JSON",
    ]:
        assert required_text in guide_text

    legacy_section = re.search(
        r"^## 手动背景与旧 token 兼容\n(?P<section>.*?)(?=^## |\Z)",
        guide_text,
        re.MULTILINE | re.DOTALL,
    )
    assert legacy_section is not None
    for required_text in [
        "SCENE", "bgm", "BGM", "兼容解析", "会忽略", "不会执行背景切换或音乐播放",
        "背景设置", "无背景", "背景音乐功能已移除",
    ]:
        assert required_text in legacy_section.group("section")
    # Retired controls must not be advertised as active entries in the token table.
    assert not re.search(r"^\| `(?:SCENE|bgm|BGM)`", guide_text, re.MULTILINE)

    assert re.search(r"未启用 ComfyUI.*\[CG\]|\[CG\].*未启用 ComfyUI", guide_text, re.DOTALL)
    assert re.search(r"t2i_provider:\s*none.*\[CG\]|\[CG\].*t2i_provider:\s*none", guide_text, re.DOTALL)

    assert re.search(r"STAT.*系统消息|系统消息.*STAT", guide_text, re.DOTALL)

    assert re.search(
        r"COT.*(默认不显示给玩家|只用于调试输出)|"
        r"(默认不显示给玩家|只用于调试输出).*COT",
        guide_text,
        re.DOTALL,
    )

    assert re.search(r"CHOICE.*\/.*2-4 个选项|2-4 个选项.*\/.*CHOICE", guide_text, re.DOTALL)

    readme_text = readme_path.read_text(encoding="utf-8")
    assert "docs/user-guides/character-template-control-tokens.md" in readme_text

    default_template_text = default_template_path.read_text(encoding="utf-8")
    assert '"CG"' in default_template_text
    assert '"STAT"' in default_template_text


def test_character_template_sample_type_selector_user_guide_is_documented() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    guide_path = repo_root / "docs" / "user-guides" / "character-template-control-tokens.md"

    guide_text = guide_path.read_text(encoding="utf-8")

    for required_text in [
        "示例类型",
        "完整示例",
        "基础对话",
        "CG 示例",
        "填入示例",
        "发布前检查",
    ]:
        assert required_text in guide_text

    sample_type_section_match = re.search(
        r"示例类型选择建议：\n(?P<section>.*?)(?=\n也可以从项目根使用命令行校验文件或标准输入：)",
        guide_text,
        re.DOTALL,
    )
    assert sample_type_section_match is not None
    sample_type_section = sample_type_section_match.group("section")

    bullet_by_name = {}
    helper_paragraphs = []
    for line in sample_type_section.splitlines():
        stripped = line.strip()
        bullet_match = re.match(r"- `(?P<name>[^`]+)`：(?P<body>.+)", stripped)
        if bullet_match:
            bullet_by_name[bullet_match.group("name")] = bullet_match.group("body")
        elif stripped:
            helper_paragraphs.append(stripped)

    assert {"完整示例", "基础对话", "CG 示例"}.issubset(bullet_by_name)

    complete_sample_bullet = bullet_by_name["完整示例"]
    assert "STAT" in complete_sample_bullet
    assert "CG" in complete_sample_bullet

    basic_dialog_bullet = bullet_by_name["基础对话"]
    assert any(phrase in basic_dialog_bullet for phrase in ["不包含", "不含", "无"])
    assert "STAT" in basic_dialog_bullet
    assert "CG" in basic_dialog_bullet

    cg_sample_bullet = bullet_by_name["CG 示例"]
    for required_text in ["speech", "prompt", "sprite", "-1"]:
        assert required_text in cg_sample_bullet

    helper_text = "\n".join(helper_paragraphs)
    assert "本地辅助" in helper_text
    assert re.search(r"不调用\s*LLM", helper_text)
    assert re.search(r"不调用\s*ComfyUI", helper_text)
    assert any(
        phrase in helper_text
        for phrase in [
            "临时 UI 状态",
            "临时",
        ]
    )
    assert any(
        phrase in helper_text
        for phrase in [
            "不会写入配置",
            "不保存",
            "不会因为 `保存配置` 单独保存为配置项",
        ]
    )
