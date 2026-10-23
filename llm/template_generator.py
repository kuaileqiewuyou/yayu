"""动态 system prompt 生成器 — 根据配置拼装完整模板。"""

from __future__ import annotations
from typing import Optional

from config.schema import Character, Background


def _structured_emotion_table(character: Character) -> str:
    rows: list[tuple[int, str]] = []
    seen_ids: set[int] = set()
    for item in getattr(character, "emotion_items", []) or []:
        if isinstance(item, dict):
            raw_id = item.get("id", 0)
            label = item.get("label", "")
            sprite_path = item.get("sprite_path", "")
        else:
            raw_id = getattr(item, "id", 0)
            label = getattr(item, "label", "")
            sprite_path = getattr(item, "sprite_path", "")
        try:
            item_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        label = str(label or "").strip()
        if item_id < 1 or item_id in seen_ids or not label or not sprite_path:
            continue
        seen_ids.add(item_id)
        rows.append((item_id, label))
    rows.sort(key=lambda pair: pair[0])
    return "\n".join(f"{item_id}: {label}" for item_id, label in rows)


def _example_sprite_id(character: Character) -> str:
    """Use an actual bound sprite, following structured-over-legacy precedence."""
    sources = (
        (getattr(character, "emotion_items", []) or [], "sprite_path", 1),
        (getattr(character, "sprites", []) or [], "path", 0),
    )
    for items, path_field, minimum_id in sources:
        available_ids: set[int] = set()
        for item in items:
            if isinstance(item, dict):
                raw_id = item.get("id")
                path = item.get(path_field, "")
            else:
                raw_id = getattr(item, "id", None)
                path = getattr(item, path_field, "")
            if not str(path or "").strip():
                continue
            try:
                item_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if item_id >= minimum_id:
                available_ids.add(item_id)
        if available_ids:
            return str(min(available_ids))
    return "-1"


def generate_system_prompt(
    character: Character,
    background: Optional[Background] = None,
    enable_narr: bool = True,
    enable_choice: bool = True,
    enable_cot: bool = True,
    skills_context: str = "",
) -> str:
    """根据角色配置动态生成 system prompt；背景仅由用户手动选择。"""
    parts: list[str] = []

    # 基础指令
    parts.append("你是一个 Galgame 中的角色。请严格按照以下规则进行对话：")
    parts.append("")

    # 角色设定
    parts.append("【角色设定】")
    parts.append(character.character_setting.strip() or "（未设定）")
    parts.append("")

    # 回复格式
    parts.append("【回复格式】")
    parts.append('你的每条回复必须是一个或多个 JSON 对象（每个对象独占一行），格式如下：')
    parts.append(f'{{"character_name": "{character.name}", "speech": "台词内容", "sprite": "立绘编号"}}')
    parts.append(f'注意：普通对话时 character_name 必须固定填写 "{character.name}"。')
    parts.append("")

    # token 说明
    parts.append("character_name 字段说明：")
    parts.append(f"- \"{character.name}\" — 普通对话（你的台词）")
    parts.append('- "STAT" — 系统/数值变化提示（例如好感度 +1、道具获得等）')
    parts.append('- "CG" — 触发 CG 文生图请求（speech 填文生图 prompt；未启用 T2I 时只显示提示）')
    parts.append('- "CARD" — 资料卡（speech 填 Markdown 正文：查询结果、步骤、代码、对比、来源链接；不会被朗读）')
    if enable_narr:
        parts.append('- "NARR" — 旁白/叙述（环境描写、动作等）')
    if enable_choice:
        parts.append('- "CHOICE" — 给玩家的选项（用 / 分隔各选项，2-4 个）')
    if enable_cot:
        parts.append('- "COT" — 你的内心思考（不会显示给玩家，放在回复开头）')

    if skills_context.strip():
        parts.append("【Skills】")
        parts.append(skills_context.strip())
        parts.append("")

    parts.append("")
    parts.append('sprite 字段：角色立绘编号（整数字符串），"-1" 表示不切换立绘')
    parts.append("")

    # 立绘对照表：结构化情绪是正式来源，本地文件路径不进入提示词。
    emotion_table = _structured_emotion_table(character) or character.emotion_tags.strip()
    if emotion_table:
        parts.append("【立绘对照表】")
        parts.append(emotion_table)
        parts.append("")

    # 示例
    example_sprite_id = _example_sprite_id(character)
    parts.append("【示例输出】")
    if enable_cot:
        parts.append(f'{{"character_name": "COT", "speech": "玩家似乎心情不错，我应该热情回应", "sprite": "-1"}}')
    parts.append(f'{{"character_name": "{character.name}", "speech": "今天天气真好呢，要不要一起出去走走？", "sprite": "{example_sprite_id}"}}')
    parts.append("")
    parts.append("【帮忙时的示例输出（台词 + 资料卡）】")
    parts.append(f'{{"character_name": "{character.name}", "speech": "查到啦～要点我整理在下面了，你看看？", "sprite": "{example_sprite_id}"}}')
    parts.append('{"character_name": "CARD", "speech": "## 结论\\n- 要点一\\n- 要点二\\n\\n## 来源\\n- [页面标题](https://example.com)", "sprite": "-1"}')
    parts.append("")

    # 规则
    parts.append("【重要规则】")
    parts.append("1. 始终保持角色扮演，不要跳出角色")
    parts.append("2. 回复只能是 JSON 对象，不要输出其他内容")
    parts.append("3. speech 字段用自然的对话语言，符合角色性格")
    parts.append("4. 根据对话情境选择合适的立绘编号")
    parts.append("5. 可以一次输出多个 JSON 对象来表达复杂场景")
    parts.append("你可以调用当前对话中提供的工具。用户要求查看或操作本地文件时，使用 terminal 等可用工具执行；不要在未尝试工具前声称无法操作。")
    parts.append(
        "用户询问项目根目录、工作区、当前工作目录或可访问目录时，必须调用 get_workspace_info 获取真实信息，不要猜测路径。"
    )
    if enable_cot:
        parts.append("6. COT 用于内心思考，放在回复开头")
    if enable_choice:
        parts.append("7. 在合适的剧情节点提供 CHOICE 选项让玩家选择")
    parts.append("CG 的 speech 填文生图 prompt，不要把 prompt 放进 sprite")
    parts.append(
        "帮用户查资料、给步骤、写代码、列清单或对比时：角色台词保持简短、只表达语气与情绪（1-2 句）；"
        "实质内容统一放进一条 CARD，用 Markdown 书写；联网查询得到的信息在 CARD 末尾列出来源链接。"
        "闲聊与剧情不要使用 CARD。"
    )
    parts.append("不确定是否该使用控制 token 时，优先使用普通角色名")

    return "\n".join(parts)
