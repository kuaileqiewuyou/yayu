from __future__ import annotations

from pathlib import Path

from core.skills.models import SkillDocument
from core.skills.parser import parse_skill_file


class SkillRepository:
    def __init__(self, roots: list[Path]):
        self.roots = [Path(root) for root in roots]

    def list_skills(self) -> list[SkillDocument]:
        skills: list[SkillDocument] = []
        for root in self.roots:
            if not root.exists():
                continue
            for skill_md_path in sorted(root.rglob("SKILL.md")):
                try:
                    skills.append(parse_skill_file(skill_md_path))
                except Exception:
                    continue
        return skills

    def get_skill(self, name: str) -> SkillDocument | None:
        normalized = name.strip().lower()
        for skill in self.list_skills():
            if skill.name.lower() == normalized:
                return skill
        return None

    def search_skills(self, query: str) -> list[SkillDocument]:
        needle = query.strip().lower()
        if not needle:
            return self.list_skills()
        results = []
        for skill in self.list_skills():
            haystacks = [skill.name.lower(), skill.description.lower(), " ".join(skill.metadata.tags).lower()]
            if any(needle in hay for hay in haystacks):
                results.append(skill)
        return results
