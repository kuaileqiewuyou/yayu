"""Named background resources preserve file identity across legacy migrations."""
from __future__ import annotations

import pytest

from config.background_assets import entries_from_background, format_resource_tags
from config.schema import Background, MediaAssetBinding


@pytest.mark.parametrize("tags", ["1-教室 2-公园", "1:教室\n2:公园", "1：教室\n2：公园"])
def test_migrates_numbered_legacy_labels_without_orphan_tags(tags):
    background = Background(
        name="场景", sprites=[{"path": "room.png"}, {"path": "park.png"}],
        bg_tags=tags + "\n3:没有对应文件",
    )

    assert entries_from_background(background) == [
        {"path": "room.png", "label": "教室"},
        {"path": "park.png", "label": "公园"},
    ]


def test_legacy_names_can_contain_spaces_and_unicode():
    background = Background(
        name="场景", sprites=[{"path":"calm.png"}, {"path":"night.png"}],
        bg_tags="1-平静 日常 🌿 2:Quiet Night 夜晚",
    )

    entries = entries_from_background(background)

    assert [entry["label"] for entry in entries] == ["平静 日常 🌿", "Quiet Night 夜晚"]
    assert format_resource_tags(entries) == "1: 平静 日常 🌿\n2: Quiet Night 夜晚"


def test_structured_names_follow_paths_after_delete_and_reorder():
    background = Background(
        name="场景", sprites=[{"path": "park.png"}, {"path": "room.png"}],
        bg_tags="1:过时教室 2:过时公园 3:过时废弃",
        scene_bindings=[
            {"path": "room.png", "label": "明亮 教室"},
            {"path": "deleted.png", "label": "已删除"},
            {"path": "park.png", "label": "夜晚 公园"},
        ],
    )

    assert entries_from_background(background) == [
        {"path": "park.png", "label": "夜晚 公园"},
        {"path": "room.png", "label": "明亮 教室"},
    ]


def test_duplicate_file_occurrences_keep_individual_names():
    background = Background(
        name="场景", sprites=[{"path":"other.png"}, {"path":"same.png"}, {"path":"same.png"}],
        scene_bindings=[
            {"path": "same.png", "label": "日间"},
            {"path": "same.png", "label": "夜间"},
            {"path": "other.png", "label": "另一首"},
        ],
    )

    assert [entry["label"] for entry in entries_from_background(background)] == [
        "另一首", "日间", "夜间",
    ]


def test_uses_current_paths_and_filename_fallback_for_missing_names():
    background = {
        "sprites": [{"path": "C:\\背景\\清晨 校园.png"}, {"path": ""}, {"path": "new.png"}],
        "scene_bindings": [{"path": "C:/背景/清晨 校园.png", "label": ""}],
        "bg_tags": "9-没有文件",
    }

    assert entries_from_background(background) == [
        {"path": "C:\\背景\\清晨 校园.png", "label": "清晨 校园"},
        {"path": "new.png", "label": "new"},
    ]
    assert format_resource_tags(entries_from_background(background)) == "1: 清晨 校园\n2: new"


def test_empty_lists_omit_orphan_structured_names_and_tags():
    background = Background(
        name="空场景", scene_bindings=[{"path": "removed.png", "label": "已删"}],
        bgm_bindings=[{"path": "removed.ogg", "label": "已删"}],
        bg_tags="1-教室", bgm_tags="1-日常",
    )

    assert entries_from_background(background) == []
    assert entries_from_background(None) == []
    assert format_resource_tags([]) == ""


def test_models_roundtrip_names_with_spaces_and_default_missing_bindings():
    background = Background(
        name="场景", sprites=[{"path": "房间.png"}], bgm_list=["日常.ogg"],
        scene_bindings=[MediaAssetBinding(path="房间.png", label="窗边 温暖的房间")],
        bgm_bindings=[{"path": "日常.ogg", "label": "Calm Morning 平静 日常"}],
    )

    reloaded = Background.model_validate_json(background.model_dump_json())

    assert reloaded == background
    assert entries_from_background(reloaded)[0]["label"] == "窗边 温暖的房间"
    assert reloaded.bgm_bindings[0].label == "Calm Morning 平静 日常"  # inert legacy values survive
    assert Background(name="旧配置").scene_bindings == []
    assert Background(name="空值", scene_bindings=None, bgm_bindings=None).bgm_bindings == []


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError, match="Unknown background resource kind"):
        entries_from_background(None, "invalid")
