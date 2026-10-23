from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from core.skills.models import SkillDocument, SkillMetadata, SkillReference

_FRONTMATTER_PATTERN = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def parse_skill_file(skill_md_path: Path) -> SkillDocument:
    content = skill_md_path.read_text(encoding="utf-8")
    frontmatter: dict[str, Any] = {}
    body = content

    match = _FRONTMATTER_PATTERN.match(content)
    if match:
        raw_frontmatter = yaml.safe_load(match.group(1)) or {}
        if not isinstance(raw_frontmatter, dict):
            raise ValueError(f"invalid frontmatter in {skill_md_path}")
        frontmatter = raw_frontmatter
        body = match.group(2).strip()

    skill_dir = skill_md_path.parent
    category = skill_dir.parent.name if skill_dir.parent != skill_dir else ""
    tags = []
    related_skills = []
    metadata_block = frontmatter.get("metadata", {})
    hermes_block = metadata_block.get("hermes", {}) if isinstance(metadata_block, dict) else {}
    if isinstance(hermes_block, dict):
        tags = [str(item) for item in hermes_block.get("tags", [])]
        related_skills = [str(item) for item in hermes_block.get("related_skills", [])]

    metadata = SkillMetadata(
        name=str(frontmatter.get("name") or skill_dir.name),
        description=str(frontmatter.get("description") or ""),
        version=str(frontmatter.get("version") or ""),
        author=str(frontmatter.get("author") or ""),
        category=category,
        tags=tags,
        related_skills=related_skills,
    )

    references_dir = skill_dir / "references"
    references = []
    if references_dir.exists():
        for path in sorted(references_dir.rglob("*.md")):
            references.append(SkillReference(path=str(path.relative_to(skill_dir)).replace("\\", "/"), absolute_path=path))

    return SkillDocument(
        metadata=metadata,
        skill_dir=skill_dir,
        skill_md_path=skill_md_path,
        raw_frontmatter=frontmatter,
        body=body,
        references=references,
    )
