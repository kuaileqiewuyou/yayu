"""
LLM JSON 中 character_name 的固定保留字。

LLM 输出的每个 JSON 对象中，character_name 字段用保留字区分消息类型：
- 普通角色名 → 对话+立绘
- COT → 思维链（不显示给用户）
- NARR → 旁白
- CHOICE → 选项
- STAT → 数值变化
- SCENE / BGM → 已停用的旧消息类型，仅识别后忽略
- CG → 触发文生图
- CARD → 信息卡片（Markdown 正文：查询结果、步骤、代码、来源等；不走 TTS）
"""

from __future__ import annotations

# --- 保留字 ---
COT = "COT"
NARR = "NARR"
CHOICE = "CHOICE"
STAT = "STAT"
SCENE = "SCENE"
BGM = "bgm"
CG = "CG"
CARD = "CARD"

# --- 兼容中文别名 ---
COT_ALIASES: frozenset[str] = frozenset({COT, "思维链"})
NARR_ALIASES: frozenset[str] = frozenset({NARR, "旁白"})
CHOICE_ALIASES: frozenset[str] = frozenset({CHOICE, "选项"})
STAT_ALIASES: frozenset[str] = frozenset({STAT, "数值"})
SCENE_ALIASES: frozenset[str] = frozenset({SCENE, "场景"})
BGM_ALIASES: frozenset[str] = frozenset({BGM, "bgm"})
CG_ALIASES: frozenset[str] = frozenset({CG, "cg"})
CARD_ALIASES: frozenset[str] = frozenset({CARD, "卡片", "INFO"})

# 系统消息（不走 TTS）
SYSTEM_DIALOG_ALIASES: frozenset[str] = (
    NARR_ALIASES | CHOICE_ALIASES | STAT_ALIASES | SCENE_ALIASES | CARD_ALIASES
)

# 需要跳过普通 UI 显示的保留字
SYSTEM_UI_SKIP: frozenset[str] = (
    CHOICE_ALIASES | STAT_ALIASES | SCENE_ALIASES
    | BGM_ALIASES | CG_ALIASES | COT_ALIASES | CARD_ALIASES
)


def normalize_name(name: str | None) -> str:
    """统一 character_name 大小写。"""
    s = (name or "").strip()
    if not s:
        return s
    low = s.casefold()
    _map = {
        "choice": CHOICE, "narr": NARR, "stat": STAT,
        "scene": SCENE, "cot": COT, "bgm": BGM, "cg": CG,
        "card": CARD, "info": CARD,
    }
    return _map.get(low, s)


def match_cot(name: str) -> bool:
    return normalize_name(name) in COT_ALIASES


def match_narr(name: str) -> bool:
    return normalize_name(name) in NARR_ALIASES


def match_choice(name: str) -> bool:
    return normalize_name(name) in CHOICE_ALIASES


def match_stat(name: str) -> bool:
    return normalize_name(name) in STAT_ALIASES


def match_scene(name: str) -> bool:
    return normalize_name(name) in SCENE_ALIASES


def match_bgm(name: str) -> bool:
    return normalize_name(name) in BGM_ALIASES


def match_cg(name: str) -> bool:
    return normalize_name(name) in CG_ALIASES


def match_card(name: str) -> bool:
    return normalize_name(name) in CARD_ALIASES


def is_system_token(name: str) -> bool:
    """是否为系统保留字（非普通角色对话）。"""
    return normalize_name(name) in SYSTEM_UI_SKIP


def is_narration(name: str) -> bool:
    """旁白需要显示但不走 TTS。"""
    return normalize_name(name) in NARR_ALIASES
