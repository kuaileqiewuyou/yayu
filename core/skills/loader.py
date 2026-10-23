from __future__ import annotations

from dataclasses import dataclass

from core.skills.models import SkillDocument


@dataclass
class LoadedSkillContent:
    name: str
    description: str
    content: str


def build_skill_context(skill: SkillDocument, *, include_references: bool = True) -> LoadedSkillContent:
    parts = []
    if skill.description:
        parts.append(f"技能说明：{skill.description}")
    if skill.body:
        parts.append(skill.body.strip())
    if include_references:
        for reference in skill.references:
            try:
                reference_text = reference.absolute_path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if reference_text:
                parts.append(f"[Reference: {reference.path}]\n{reference_text}")
    return LoadedSkillContent(
        name=skill.name,
        description=skill.description,
        content="\n\n".join(part for part in parts if part).strip(),
    )


def build_skills_context(skills: list[SkillDocument]) -> str:
    loaded = [build_skill_context(skill) for skill in skills]
    sections = []
    for item in loaded:
        if item.content:
            sections.append(f"## {item.name}\n{item.content}")
    return "\n\n".join(sections).strip()
