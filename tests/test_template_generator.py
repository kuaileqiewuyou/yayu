from pathlib import Path
import json

import pytest

from config.schema import Background, Character
from llm.template_generator import generate_system_prompt


@pytest.mark.parametrize(
    ("assets", "expected_id"),
    [
        ({"emotion_items": [{"id": 1, "label": "眨眼微笑", "sprite_path": "xiaoya.png"}]}, "1"),
        ({"emotion_items": [{"id": 2, "label": "happy", "sprite_path": "happy.png"}]}, "2"),
        ({"sprites": [{"id": 5, "path": "legacy.png"}]}, "5"),
        ({"emotion_tags": "2: 只有文字标签，没有图片"}, "-1"),
        ({"emotion_items": [
            {"id": 1, "label": "未绑定", "sprite_path": ""},
            {"id": 2, "label": "空白路径", "sprite_path": "  "},
            {"id": 7, "label": "neutral", "sprite_path": "neutral.png"},
        ]}, "7"),
        ({"emotion_items": [{"id": 2, "label": "未绑定", "sprite_path": ""}],
          "sprites": [{"id": 0, "path": "legacy.png"}]}, "0"),
        ({"emotion_items": [{"id": 1, "label": "未绑定", "sprite_path": ""}],
          "sprites": [{"id": 2, "path": ""}]}, "-1"),
        ({"emotion_items": [
            {"id": 3, "label": "happy", "sprite_path": "happy.png"},
            {"id": 1, "label": "neutral", "sprite_path": "neutral.png"},
        ], "sprites": [{"id": 0, "path": "legacy.png"}]}, "1"),
    ],
    ids=("xiaoya-only-one", "only-two", "legacy-stable-id", "labels-without-assets",
         "ignore-empty-paths", "fallback-to-legacy", "no-valid-assets", "structured-priority"),
)
def test_prompt_dialogue_examples_only_use_bound_sprite_ids(assets, expected_id):
    character = Character(name="小芽", character_setting="温柔机灵的故事整理员", **assets)

    prompt = generate_system_prompt(character)

    example_section = prompt.split("【示例输出】", 1)[1].split("【重要规则】", 1)[0]
    samples = [json.loads(line) for line in example_section.splitlines() if line.startswith("{")]
    dialogue_samples = [sample for sample in samples if sample["character_name"] == "小芽"]
    assert len(dialogue_samples) == 2
    assert {sample["sprite"] for sample in dialogue_samples} == {expected_id}


def test_prompt_uses_configured_character_name_in_json_format_example():
    character = Character(name="诺艾尔", character_setting="温柔可靠", emotion_tags="0: neutral")

    prompt = generate_system_prompt(character)

    assert '{"character_name": "诺艾尔", "speech": "台词内容", "sprite": "立绘编号"}' in prompt
    assert '普通对话时 character_name 必须固定填写 "诺艾尔"' in prompt
    assert '{"character_name": "角色名"' not in prompt


def test_prompt_documents_stat_and_cg_control_tokens_by_default():
    character = Character(name="诺艾尔", character_setting="温柔可靠", emotion_tags="0: neutral")

    prompt = generate_system_prompt(character)

    assert '"STAT" — 系统/数值变化提示' in prompt
    assert '"CG" — 触发 CG 文生图请求' in prompt
    assert 'CG 的 speech 填文生图 prompt' in prompt


def test_prompt_tells_model_to_use_available_tools_for_local_file_requests():
    character = Character(name="诺艾尔", character_setting="温柔可靠")

    prompt = generate_system_prompt(character)

    assert "本地文件" in prompt
    assert "terminal" in prompt
    assert "不要在未尝试工具前声称无法操作" in prompt


def test_prompt_requires_workspace_info_tool_for_root_directory_questions():
    character = Character(name="诺艾尔", character_setting="温柔可靠")

    prompt = generate_system_prompt(character)

    assert "项目根目录" in prompt
    assert "get_workspace_info" in prompt
    assert "不要猜测路径" in prompt


def test_prompt_stat_and_cg_are_present_when_optional_story_tokens_disabled():
    character = Character(name="诺艾尔", character_setting="温柔可靠", emotion_tags="0: neutral")

    prompt = generate_system_prompt(character, enable_narr=False, enable_choice=False, enable_cot=False)

    assert '"STAT" — 系统/数值变化提示' in prompt
    assert '"CG" — 触发 CG 文生图请求' in prompt
    assert '"NARR"' not in prompt
    assert '"CHOICE"' not in prompt
    assert '"COT"' not in prompt


def test_prompt_excludes_retired_scene_and_music_controls_even_for_legacy_configuration():
    character = Character(name="诺艾尔", character_setting="温柔可靠")
    background = Background.model_validate({
        "name": "旧场景组",
        "sprites": [{"path": "D:/private/room.png"}],
        "bg_tags": "1: 旧场景名称",
        "bgm_list": ["D:/private/music.ogg"],
        "bgm_tags": "1: 旧音乐名称",
    })

    prompt = generate_system_prompt(character, background=background)

    for retired_text in ("SCENE", "bgm", "BGM", "场景对照表", "BGM 对照表", "旧场景名称", "旧音乐名称", "D:/private"):
        assert retired_text not in prompt
    assert "角色立绘编号" in prompt


def test_default_template_does_not_offer_retired_model_resource_controls():
    template_path = Path(__file__).resolve().parents[1] / "data" / "character_templates" / "default.txt"
    template = template_path.read_text(encoding="utf-8")

    for retired_token in ("SCENE", "bgm", "BGM"):
        assert retired_token not in template
    assert "角色立绘编号" in template


def test_character_structured_emotion_items_are_available_as_formal_schema():
    character = Character(
        name="诺艾尔",
        character_setting="温柔可靠",
        emotion_tags="0: neutral",
        emotion_items=[
            {"id": 1, "label": "neutral", "sprite_path": "neutral.png"},
            {"id": 2, "label": "happy", "sprite_path": "happy.png"},
        ],
    )

    assert len(character.emotion_items) == 2
    assert character.emotion_items[0].id == 1
    assert character.emotion_items[0].label == "neutral"
    assert character.emotion_items[0].sprite_path == "neutral.png"
    assert character.emotion_items[1].id == 2
    assert character.emotion_items[1].label == "happy"
    assert character.emotion_items[1].sprite_path == "happy.png"


def test_prompt_uses_structured_emotion_ids_without_exposing_local_paths():
    character = Character(
        name="诺艾尔",
        character_setting="温柔可靠",
        emotion_tags="0: legacy-neutral",
        emotion_items=[
            {"id": 2, "label": "happy", "sprite_path": "D:/Pictures/noelle-happy.png"},
            {"id": 1, "label": "neutral", "sprite_path": "D:/Pictures/noelle-neutral.png"},
        ],
    )

    prompt = generate_system_prompt(character)

    assert "【立绘对照表】\n1: neutral\n2: happy" in prompt
    assert "legacy-neutral" not in prompt
    assert "D:/Pictures" not in prompt
    assert ".png" not in prompt


def test_character_emotion_item_one_is_the_first_sprite_source():
    character = Character(
        name="诺艾尔",
        character_setting="温柔可靠",
        emotion_tags="0: neutral",
        emotion_items=[
            {"id": 1, "label": "neutral", "sprite_path": "neutral.png"},
            {"id": 2, "label": "happy", "sprite_path": "happy.png"},
        ],
    )

    assert character.emotion_items[0].id == 1
    assert character.primary_sprite_path == "neutral.png"


def test_character_allows_legacy_fields_to_coexist_while_structured_emotion_items_remain_formal_source():
    character = Character(
        name="诺艾尔",
        character_setting="温柔可靠",
        emotion_tags="0: legacy-neutral\n1: legacy-happy",
        sprites=[
            {"path": "legacy-first.png"},
            {"path": "legacy-second.png"},
        ],
        emotion_items=[
            {"id": 1, "label": "neutral", "sprite_path": "structured-neutral.png"},
            {"id": 2, "label": "happy", "sprite_path": "structured-happy.png"},
        ],
    )

    assert character.emotion_tags == "0: legacy-neutral\n1: legacy-happy"
    assert character.sprites[0].path == "legacy-first.png"
    assert character.emotion_items[0].id == 1
    assert character.emotion_items[0].sprite_path == "structured-neutral.png"
    assert character.primary_sprite_path == "structured-neutral.png"


def test_character_prefers_structured_emotion_items_over_legacy_fields_for_primary_sprite():
    character = Character(
        name="诺艾尔",
        character_setting="温柔可靠",
        emotion_tags="0: legacy-neutral\n1: legacy-happy",
        sprites=[
            {"path": "legacy-first.png"},
            {"path": "legacy-second.png"},
        ],
        emotion_items=[
            {"id": 1, "label": "neutral", "sprite_path": "structured-neutral.png"},
            {"id": 2, "label": "happy", "sprite_path": "structured-happy.png"},
        ],
    )

    assert character.primary_sprite_path == "structured-neutral.png"


def test_character_emotion_items_formal_ids_start_from_one_instead_of_zero():
    character = Character(
        name="诺艾尔",
        character_setting="温柔可靠",
        emotion_tags="0: neutral",
        emotion_items=[
            {"id": 0, "label": "legacy-neutral", "sprite_path": "legacy-neutral.png"},
            {"id": 1, "label": "happy", "sprite_path": "happy.png"},
        ],
    )

    assert character.emotion_items[0].id == 1
    assert character.primary_sprite_path == "legacy-neutral.png"
