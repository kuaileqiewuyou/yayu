"""Validate public user documentation without loading runtime or private config."""
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"
TESTING_GUIDE = ROOT / "docs" / "testing.md"
TEMPLATE_GUIDE = ROOT / "docs" / "user-guides" / "character-template-control-tokens.md"
MEMORY_GUIDE = ROOT / "docs" / "user-guides" / "memory.md"
SPRITE_GUIDE = ROOT / "docs" / "user-guides" / "sprite-pack.md"
PUBLIC_DOCS = (README, CONTRIBUTING, TESTING_GUIDE, TEMPLATE_GUIDE, MEMORY_GUIDE, SPRITE_GUIDE)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    """Return a section through the next heading of the same or higher level."""
    lines = text.splitlines()
    level = len(heading) - len(heading.lstrip("#"))
    start = lines.index(heading) + 1
    section = []
    for line in lines[start:]:
        match = re.match(r"^(#{1,6})\s", line)
        if match and len(match.group(1)) <= level:
            break
        section.append(line)
    return "\n".join(section)


def _assert_has_terms(fragment: str, *terms: str) -> None:
    for term in terms:
        assert term in fragment


@pytest.mark.parametrize("document", PUBLIC_DOCS, ids=lambda path: path.name)
def test_public_document_local_links_resolve_inside_the_repository(document: Path) -> None:
    text = _read(document)
    # Covers Markdown links/images and the README's HTML hero image.
    links = re.findall(r"!?\[[^\]]*\]\(([^\s)]+)(?:\s+[^)]*)?\)", text)
    links += re.findall(r"(?:src|href)=[\"']([^\"']+)[\"']", text)
    for link in links:
        parsed = urlsplit(link.strip("<>"))
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        target = (document.parent / unquote(parsed.path)).resolve()
        assert target.is_relative_to(ROOT), f"Link escapes repository: {document.name}: {link}"
        assert target.exists(), f"Broken local link: {document.name}: {link}"


def test_readme_documents_executable_startup_and_private_configuration() -> None:
    readme = _read(README)
    _assert_has_terms(readme, "requirements.txt", "init_config.py", "webui_qt.py", "main.py")
    _assert_has_terms(readme, "api.local.yaml", "API Key", "聊天", "本机", "Git")
    for script in ("scripts/init_config.py", "webui_qt.py", "main.py"):
        assert (ROOT / script).is_file()


def test_readme_links_feature_details_to_public_user_guides() -> None:
    readme = _read(README)
    for path in (CONTRIBUTING, TESTING_GUIDE, TEMPLATE_GUIDE, MEMORY_GUIDE, SPRITE_GUIDE):
        assert path.relative_to(ROOT).as_posix() in readme
    # A fresh checkout must not need an author's development diary or machine setup.
    assert "docs/manual-tests/" not in readme
    assert "docs/project-status.md" not in readme


def test_readme_keeps_optional_services_and_tool_safety_boundaries_visible() -> None:
    readme = _read(README)
    _assert_has_terms(readme, "TTS", "CG", "默认关闭", "ComfyUI", "workflow")
    _assert_has_terms(readme, "终端", "人工批准", "ASR", "未接入")
    assert "t2i_provider: none" in readme or "CG 默认关闭" in readme


def test_contributing_documents_full_and_focused_offline_validation() -> None:
    contributing = _read(CONTRIBUTING)
    _assert_has_terms(contributing, "pytest pytest-qt", "python -E -m pytest -q")
    _assert_has_terms(contributing, "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "QT_QPA_PLATFORM", "offscreen")
    _assert_has_terms(contributing, "完整", "sys.modules", "临时配置", "真实 API Key", "winpty")
    for path in re.findall(r"tests/test_[\w]+\.py", contributing):
        assert (ROOT / path).is_file()


def test_public_docs_do_not_require_personal_checkout_paths_or_internal_records() -> None:
    for document in PUBLIC_DOCS:
        text = _read(document)
        # Generic examples such as path/to/file and repository-relative commands
        # are portable. An absolute personal home or development tree is not.
        assert not re.search(r"[A-Za-z]:[/\\](?:Users|Develop)[/\\]", text)
        assert not re.search(r"/mnt/[a-z]/(?:Users|Develop)/", text)
        assert "docs/superpowers/" not in text


def test_template_guide_basic_and_cg_examples_are_valid_json_lines() -> None:
    guide = _read(TEMPLATE_GUIDE)
    for heading in ("## 输出格式", "## CG 示例"):
        blocks = re.findall(r"```json\s*\n(.*?)```", _section(guide, heading), flags=re.DOTALL)
        assert blocks
        for block in blocks:
            for line in block.splitlines():
                if not line.strip():
                    continue
                payload = json.loads(line)
                assert isinstance(payload, dict)
                assert {"character_name", "speech", "sprite"} <= payload.keys()
                assert payload["character_name"]


def test_template_guide_documents_control_tokens_and_cg_prompt_fields() -> None:
    guide = _read(TEMPLATE_GUIDE)
    token_table = _section(guide, "## 控制 token 表")
    _assert_has_terms(token_table, "NARR", "CHOICE", "STAT", "CARD", "CG")
    assert "SCENE" not in token_table
    assert "BGM" not in token_table
    cg_section = _section(guide, "## CG 示例")
    _assert_has_terms(cg_section, "speech", "prompt", "t2i_provider: none", "不会提交生成")


def test_template_guide_describes_manual_backgrounds_and_retired_controls() -> None:
    section = _section(_read(TEMPLATE_GUIDE), "## 手动背景与旧 token 兼容")
    _assert_has_terms(section, "背景设置", "保存配置", "顶栏", "无背景", "透明背景")
    _assert_has_terms(section, "不会发送聊天消息或调用模型", "SCENE", "bgm", "BGM", "兼容解析")
    _assert_has_terms(section, "会忽略", "不会执行背景切换或音乐播放", "背景音乐功能已移除")


def test_template_guide_preflight_explains_errors_warnings_and_fixes() -> None:
    section = _section(_read(TEMPLATE_GUIDE), "### 发布前检查的修复建议")
    _assert_has_terms(section, "错误或警告", "修复建议：", "检查通过时不会显示修复建议")
    _assert_has_terms(section, "角色名称为空", "没有示例输出", "填入示例", "缺少 `sprite`", '"-1"')
    _assert_has_terms(section, "角色性格", "称呼方式", "对话边界", "情绪标签为空")
    _assert_has_terms(section, "CG", "prompt", "speech", "sprite")
    _assert_has_terms(section, "严重错误", "取消保存", "只有警告", "仍会保存")


def test_template_guide_documents_handoff_without_automatic_publication() -> None:
    section = _section(_read(TEMPLATE_GUIDE), "### 模板发布前交接清单")
    _assert_has_terms(section, "生成发布清单", "角色模板发布清单", "复制结果", "发布前检查")
    _assert_has_terms(section, "角色名称", "角色设定", "情绪标签", "示例输出", "控制 token 覆盖")
    _assert_has_terms(section, "NARR", "CHOICE", "STAT", "CG", "修复建议", "聊天", "冒烟")
    _assert_has_terms(section, "本地轻量", "不是完整模板市场", "多示例管理", "不会自动发布")


def test_template_guide_documents_drafts_and_temporary_offline_examples() -> None:
    section = _section(_read(TEMPLATE_GUIDE), "### 导出模板发布草稿")
    _assert_has_terms(section, "导出发布草稿", "角色模板发布草稿", "Markdown")
    _assert_has_terms(section, "角色名称", "角色设定", "情绪标签", "示例输出", "控制 token 覆盖")
    _assert_has_terms(section, "发布前检查未通过", "阻止导出", "发布前检查有警告", "允许导出")
    _assert_has_terms(section, "完整示例", "基础对话", "情绪切换示例", "CG 示例", "剧情分支示例")
    _assert_has_terms(section, "模板复用示例", "模板修正示例", "复核", "警告", "重新检查")
    _assert_has_terms(section, "临时 UI 状态", "不会写入配置", "不调用 LLM", "不调用 ComfyUI")


def test_template_release_package_documents_contents_and_privacy_boundaries() -> None:
    section = _section(_read(TEMPLATE_GUIDE), "### 导出模板发布包")
    _assert_has_terms(section, "README.md", "角色模板发布草稿.md", "template-output.jsonl")
    _assert_has_terms(section, "preflight-report.txt", "metadata.json", "template-data.json")
    _assert_has_terms(section, "私有 API 配置", "聊天历史", "本机服务配置", "不会自动上传")


def test_template_library_documents_explicit_import_and_save() -> None:
    section = _section(_read(TEMPLATE_GUIDE), "### 本地模板库")
    _assert_has_terms(section, "保存到模板库", "导入选中模板", "data/templates/packages/")
    _assert_has_terms(section, "本地", "离线", "轻量", "确认是否覆盖", "重新运行示例输出校验")
    _assert_has_terms(section, "不会直接写入", "characters.yaml", "保存配置")
    _assert_has_terms(section, "不包含私有 API 配置", "聊天历史", "本机服务配置")


def test_memory_guide_documents_local_storage_model_usage_and_scope() -> None:
    guide = _read(MEMORY_GUIDE)
    _assert_has_terms(guide, "data/chat_history/sessions/*.json", "memory.sqlite3", "Git 忽略")
    _assert_has_terms(guide, "额外模型用量", "来源", "待核实", "全新剧情", "长期记忆")
    _assert_has_terms(guide, "删除", "回溯", "不会", "不连接真实模型服务")


def test_sprite_guide_documents_deletion_ownership_and_save_failure() -> None:
    guide = _read(SPRITE_GUIDE)
    _assert_has_terms(guide, "放大预览", "删除选中立绘", "剩余立绘编号不变", "保存配置")
    _assert_has_terms(guide, "外部原始导入文件", "其他角色", "保存失败", "待删除记录")
