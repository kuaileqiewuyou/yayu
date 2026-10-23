from pathlib import Path

from core.skills.loader import build_skill_context, build_skills_context
from core.skills.parser import parse_skill_file
from core.skills.repository import SkillRepository


def test_parse_skill_file_reads_frontmatter_and_body(tmp_path: Path):
    skill_dir = tmp_path / "dialogue" / "romance-dialogue"
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\nname: romance-dialogue\ndescription: romance skill\nmetadata:\n  hermes:\n    tags: [romance]\n---\n\n# Title\n\nUse gentle romantic pacing.\n",
        encoding="utf-8",
    )

    doc = parse_skill_file(skill_md)

    assert doc.name == "romance-dialogue"
    assert doc.description == "romance skill"
    assert "Use gentle romantic pacing." in doc.body
    assert doc.metadata.tags == ["romance"]


def test_skill_repository_lists_and_finds_skills(tmp_path: Path):
    skill_dir = tmp_path / "dialogue" / "romance-dialogue"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: romance-dialogue\ndescription: romance skill\n---\n\nBody\n", encoding="utf-8")

    repository = SkillRepository([tmp_path])

    skills = repository.list_skills()
    assert len(skills) == 1
    assert repository.get_skill("romance-dialogue") is not None
    assert repository.search_skills("romance")[0].name == "romance-dialogue"


def test_build_skills_context_includes_references(tmp_path: Path):
    skill_dir = tmp_path / "plot" / "mystery"
    references_dir = skill_dir / "references"
    references_dir.mkdir(parents=True)
    (references_dir / "notes.md").write_text("clue note", encoding="utf-8")
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("---\nname: mystery\ndescription: suspense\n---\n\nBody\n", encoding="utf-8")

    skill = parse_skill_file(skill_md)
    loaded = build_skill_context(skill)
    merged = build_skills_context([skill])

    assert "clue note" in loaded.content
    assert "## mystery" in merged
