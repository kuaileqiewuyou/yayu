import pytest

from sdk.messages import LLMDialogMessage, TTSOutputMessage
from core.runtime.ui_message_router import route_llm_dialog, route_tts_output


def test_route_llm_dialog_hides_cot():
    msg = LLMDialogMessage(name="COT", text="内部思考", asset_id="-1")

    assert route_llm_dialog(msg, active_character_name="诺艾尔") == []


def test_route_llm_dialog_shows_character_message():
    msg = LLMDialogMessage(name="诺艾尔", text="欢迎回来。", asset_id="1")

    events = route_llm_dialog(msg, active_character_name="诺艾尔")

    assert len(events) == 1
    assert events[0].kind == "dialog"
    assert events[0].payload is msg


def test_route_llm_dialog_ignores_choice_during_immediate_phase():
    msg = LLMDialogMessage(name="CHOICE", text="继续 / 离开 / 休息", asset_id="-1")

    assert route_llm_dialog(msg, active_character_name="诺艾尔") == []


def test_route_llm_dialog_ignores_narr_during_immediate_phase():
    msg = LLMDialogMessage(name="NARR", text="阳光洒进房间。", asset_id="-1")

    assert route_llm_dialog(msg, active_character_name="诺艾尔") == []


def test_route_tts_output_routes_cot_to_debug_signal():
    out = TTSOutputMessage(name="COT", text="内部思考", asset_id="-1")

    events = route_tts_output(out)

    assert len(events) == 1
    assert events[0].kind == "cot"
    assert events[0].payload == "内部思考"


def test_route_tts_output_shows_character_message():
    out = TTSOutputMessage(name="诺艾尔", text="欢迎回来。", asset_id="1", audio_path="voice.wav")

    events = route_tts_output(out)

    assert len(events) == 1
    assert events[0].kind == "dialog"
    assert events[0].payload is out


def test_route_tts_output_routes_choice_to_options():
    out = TTSOutputMessage(name="CHOICE", text="继续 / 离开 / 休息", asset_id="-1")

    events = route_tts_output(out)

    assert len(events) == 1
    assert events[0].kind == "options"
    assert events[0].payload == ["继续", "离开", "休息"]


def test_route_tts_output_routes_narr_to_narration():
    out = TTSOutputMessage(name="NARR", text="阳光洒进房间。", asset_id="-1")

    events = route_tts_output(out)

    assert len(events) == 1
    assert events[0].kind == "narration"
    assert events[0].payload == "阳光洒进房间。"


@pytest.mark.parametrize("name", ["SCENE", "scene", "场景", "BGM", "bgm", "BgM"])
def test_retired_model_resource_controls_are_silently_discarded_in_both_phases(name):
    dialog = LLMDialogMessage(name=name, text="旧回复中的资源控制指令", asset_id="1")
    output = TTSOutputMessage(name=name, text=dialog.text, asset_id="1", audio_path="unused.ogg")

    # Even if an old character/template used a reserved name, these must never
    # overwrite the user's selected background or fall through to audio/dialogue.
    assert route_llm_dialog(dialog, active_character_name=name) == []
    assert route_tts_output(output) == []
