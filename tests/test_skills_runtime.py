from queue import Queue
from pathlib import Path
from types import SimpleNamespace
import pytest

from core.runtime.app_runtime import AppRuntime, set_app_runtime
import core.runtime.app_runtime as app_runtime
from core.skills.runtime import build_session_skills_context, resolve_effective_skill_names
from core.sprite import chat_history
from llm.template_generator import generate_system_prompt


@pytest.fixture(autouse=True)
def isolated_history_runtime(monkeypatch):
    """Skills unit tests must not reuse a UI test's partially torn-down runtime."""
    monkeypatch.setattr(app_runtime, "_app_runtime", None)
    monkeypatch.setattr(chat_history, "_active_session_id", None)
    monkeypatch.setattr(chat_history, "chat_history", [])
    store = chat_history.get_session_store()
    yield
    chat_history.set_session_store(store)


class FakeLLMManager:
    def __init__(self):
        self._messages = [{"role": "system", "content": "base"}]

    def get_messages(self):
        return list(self._messages)

    def set_messages(self, messages):
        self._messages = list(messages)

    def clear_history(self):
        self._messages = [m for m in self._messages if m.get("role") == "system"]


def test_build_session_skills_context_uses_active_session_enabled_skills(tmp_path: Path, monkeypatch):
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "dialogue" / "romance-dialogue"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: romance-dialogue\ndescription: romance skill\n---\n\nPrefer affectionate dialogue.\n",
        encoding="utf-8",
    )

    history_root = tmp_path / "history"
    chat_history.set_session_store(
        chat_history.SessionStore(
            history_root=history_root,
            sessions_dir=history_root / "sessions",
            index_path=history_root / "sessions.json",
            legacy_default_file=history_root / "default.json",
        )
    )
    session = chat_history.create_session(title="会话一", character_name="诺艾尔", make_active=True)
    chat_history.update_session_enabled_skills(session.id, ["romance-dialogue"])
    chat_history.switch_session(session.id)
    set_app_runtime(AppRuntime(config=None, llm_manager=FakeLLMManager(), tts_manager=None,
                               user_input_queue=Queue(), tts_queue=Queue(), audio_path_queue=Queue()))

    context = build_session_skills_context(skills_root)

    assert "romance-dialogue" in context
    assert "Prefer affectionate dialogue." in context


def test_generate_system_prompt_includes_skills_section_when_present():
    character = SimpleNamespace(name="诺艾尔", character_setting="温柔", emotion_tags="")
    prompt = generate_system_prompt(character=character, background=None, skills_context="## romance-dialogue\nPrefer affectionate dialogue.")

    assert "【Skills】" in prompt
    assert "Prefer affectionate dialogue." in prompt


def test_resolve_effective_skill_names_merges_global_character_and_session_in_order():
    names = resolve_effective_skill_names(
        global_default_skills=["shared", "global-a"],
        character_default_skills=["shared", "character-a"],
        session_enabled_skills=["character-a", "session-a"],
    )

    assert names == ["shared", "global-a", "character-a", "session-a"]


def test_build_session_skills_context_uses_session_enabled_skills_as_effective_source(tmp_path: Path):
    skills_root = tmp_path / "skills"
    for category, skill_name, body in [
        ("base", "shared", "Shared skill."),
        ("base", "global-a", "Global skill."),
        ("character", "character-a", "Character skill."),
        ("session", "session-a", "Session skill."),
    ]:
        skill_dir = skills_root / category / skill_name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {skill_name}\ndescription: test\n---\n\n{body}\n",
            encoding="utf-8",
        )

    history_root = tmp_path / "history-merged"
    chat_history.set_session_store(
        chat_history.SessionStore(
            history_root=history_root,
            sessions_dir=history_root / "sessions",
            index_path=history_root / "sessions.json",
            legacy_default_file=history_root / "default.json",
        )
    )
    session = chat_history.create_session(title="会话二", character_name="诺艾尔", make_active=True)
    chat_history.update_session_enabled_skills(session.id, ["shared", "session-a"])
    chat_history.switch_session(session.id)

    context = build_session_skills_context(
        skills_root,
        global_default_skills=["global-a"],
        character_default_skills=["shared", "character-a"],
    )

    assert "## shared" in context
    assert "## session-a" in context
    assert "## global-a" not in context
    assert "## character-a" not in context
