from types import SimpleNamespace

from core.runtime.display_logic import should_display_llm_message


def test_displays_plain_llm_dialog_message_without_is_system_message_attribute():
    msg = SimpleNamespace(name="小雪", text="你好", asset_id="0")

    assert should_display_llm_message(msg, active_character_name="诺艾尔") is True


def test_displays_active_character_even_if_marked_system_message():
    msg = SimpleNamespace(name="小雪", text="你好", asset_id="0", is_system_message=True)

    assert should_display_llm_message(msg, active_character_name="小雪") is True


def test_displays_narration_message():
    msg = SimpleNamespace(name="NARR", text="阳光洒进房间。", asset_id="-1")

    assert should_display_llm_message(msg, active_character_name="小雪") is True


def test_hides_cot_message():
    msg = SimpleNamespace(name="COT", text="思考", asset_id="-1")

    assert should_display_llm_message(msg, active_character_name="小雪") is False


def test_hides_choice_control_message_from_normal_bubble():
    msg = SimpleNamespace(name="CHOICE", text="继续/离开", asset_id="-1")

    assert should_display_llm_message(msg, active_character_name="小雪") is False
