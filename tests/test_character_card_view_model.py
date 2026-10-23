from types import SimpleNamespace

import pytest

from ui.settings_ui.character_card_view_model import build_character_card_view_model


@pytest.mark.parametrize(
    ("character", "expected_source"),
    [
        (
            SimpleNamespace(
                name="头像角色",
                avatar="explicit-avatar.png",
                primary_sprite_path="structured-default.png",
                sprites=[{"path": "legacy-first.png"}],
                emotion_items=[{"id": 1, "label": "neutral", "sprite_path": "structured-default.png"}],
            ),
            "explicit-avatar.png",
        ),
        (
            SimpleNamespace(
                name="结构化头像角色",
                avatar="",
                primary_sprite_path="structured-default.png",
                sprites=[{"path": "legacy-first.png"}],
                emotion_items=[{"id": 1, "label": "neutral", "sprite_path": "structured-default.png"}],
            ),
            "structured-default.png",
        ),
        (
            SimpleNamespace(
                name="legacy回退角色",
                avatar="",
                primary_sprite_path="",
                sprites=[{"path": "legacy-first.png"}, {"path": "legacy-second.png"}],
                emotion_items=[{"id": 1, "label": "neutral", "sprite_path": ""}],
            ),
            "legacy-first.png",
        ),
        (
            SimpleNamespace(
                name="占位头像角色",
                avatar="",
                primary_sprite_path="",
                sprites=[],
                emotion_items=[],
            ),
            "",
        ),
    ],
)
def test_character_card_view_model_keeps_placeholder_text_and_exposes_avatar_source(character, expected_source):
    view_model = build_character_card_view_model(character, placeholder_text="头像")

    assert view_model.avatar_text == "头像"
    assert view_model.avatar_source == expected_source


def test_character_card_view_model_formats_overview_stats():
    character = SimpleNamespace(
        name="统计角色",
        avatar="",
        primary_sprite_path="",
        sprites=[{"path": "a.png"}, {"path": "b.png"}],
        emotion_items=[
            {"id": 1, "label": "neutral", "sprite_path": "a.png"},
            {"id": 2, "label": "happy", "sprite_path": "b.png"},
            {"id": 3, "label": "sad", "sprite_path": ""},
        ],
    )

    view_model = build_character_card_view_model(character, placeholder_text="头像")

    assert view_model.name == "统计角色"
    assert view_model.stats_text == "2 张立绘 · 3 个情绪"
