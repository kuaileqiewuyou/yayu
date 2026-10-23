from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SkillReference:
    path: str
    absolute_path: Path


@dataclass
class SkillMetadata:
    name: str
    description: str = ""
    version: str = ""
    author: str = ""
    category: str = ""
    tags: list[str] = field(default_factory=list)
    related_skills: list[str] = field(default_factory=list)


@dataclass
class SkillDocument:
    metadata: SkillMetadata
    skill_dir: Path
    skill_md_path: Path
    raw_frontmatter: dict
    body: str
    references: list[SkillReference] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def description(self) -> str:
        return self.metadata.description
