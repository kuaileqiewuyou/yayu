from dataclasses import dataclass

from core.runtime.ui_worker_handlers import UIWorkerHandlers
from sdk.messages import TTSOutputMessage


class FakeWindow:
    def __init__(self):
        self.messages = []
        self.options = []
        self.backgrounds = []
        self.statuses = []

    def add_message(self, text, is_user=False, char_name="", char_color="#f2a0bd"):
        self.messages.append({
            "text": text,
            "is_user": is_user,
            "char_name": char_name,
            "char_color": char_color,
        })

    def post_options(self, options):
        self.options.append(options)

    def set_background(self, path):
        self.backgrounds.append(path)

    def set_reply_status(self, text, error=False):
        self.statuses.append({"text": text, "error": error})


@dataclass
class FakeConfig:
    backgrounds: list


def make_handlers(config=None, audio_calls=None, submit_t2i_prompt=None):
    window = FakeWindow()
    config = config if config is not None else FakeConfig(backgrounds=[])
    audio_calls = audio_calls if audio_calls is not None else []
    return UIWorkerHandlers(window, config, audio_calls.append, submit_t2i_prompt=submit_t2i_prompt), window, audio_calls


def test_on_update_dialog_plays_audio_when_path_present():
    handlers, _, audio_calls = make_handlers()
    out = TTSOutputMessage(name="诺艾尔", text="你好", asset_id="1", audio_path="voice.wav")

    handlers.on_update_dialog(out)

    assert audio_calls == ["voice.wav"]


def test_on_update_dialog_ignores_missing_audio_path():
    handlers, _, audio_calls = make_handlers()
    out = TTSOutputMessage(name="诺艾尔", text="你好", asset_id="1", audio_path="")

    handlers.on_update_dialog(out)

    assert audio_calls == []


def test_on_update_dialog_reports_tts_error_to_status():
    handlers, window, audio_calls = make_handlers()
    out = TTSOutputMessage(
        name="诺艾尔",
        text="你好",
        asset_id="1",
        audio_path="",
        error="语音合成失败：boom",
    )

    handlers.on_update_dialog(out)

    assert audio_calls == []
    assert window.statuses == [{"text": "语音合成失败：boom", "error": True}]


def test_on_update_dialog_reports_audio_playback_failure():
    handlers, window, _ = make_handlers(audio_calls=None)
    handlers.play_audio = lambda path: False
    out = TTSOutputMessage(name="诺艾尔", text="你好", asset_id="1", audio_path="missing.wav")

    handlers.on_update_dialog(out)

    assert window.statuses == [{"text": "语音播放失败：missing.wav", "error": True}]


def test_on_update_narration_adds_narrator_message():
    handlers, window, _ = make_handlers()

    handlers.on_update_narration("阳光洒进房间。")

    assert window.messages == [
        {"text": "阳光洒进房间。", "is_user": False, "char_name": "旁白", "char_color": "#AAAAAA"},
    ]


def test_on_update_options_posts_options():
    handlers, window, _ = make_handlers()

    handlers.on_update_options(["继续", "离开"])

    assert window.options == [["继续", "离开"]]


def test_on_update_cg_adds_system_prompt_message():
    handlers, window, _ = make_handlers()

    handlers.on_update_cg("生成一张夕阳 CG")

    assert window.messages == [
        {"text": "[CG] 生成一张夕阳 CG", "is_user": False, "char_name": "系统", "char_color": "#84C2D5"},
    ]
    assert window.statuses == []


def test_on_update_cg_submits_prompt_when_submitter_is_available():
    submitted = []
    handlers, window, _ = make_handlers(submit_t2i_prompt=submitted.append)

    handlers.on_update_cg("夕阳下的教室")

    assert submitted == ["夕阳下的教室"]
    assert window.messages == [
        {"text": "[CG] 夕阳下的教室", "is_user": False, "char_name": "系统", "char_color": "#84C2D5"},
    ]
    assert window.statuses == [{"text": "CG 生成已提交，正在等待 ComfyUI 生成…", "error": False}]


def test_on_update_stat_adds_system_message():
    handlers, window, _ = make_handlers()

    handlers.on_update_stat("好感度 +1")

    assert window.messages == [
        {"text": "好感度 +1", "is_user": False, "char_name": "系统", "char_color": "#84C2D5"},
    ]


def test_on_update_cot_prints_non_empty_text(capsys):
    handlers, _, _ = make_handlers()

    handlers.on_update_cot("内部思考")

    assert "[COT] 内部思考" in capsys.readouterr().out


def test_on_update_cot_ignores_empty_text(capsys):
    handlers, _, _ = make_handlers()

    handlers.on_update_cot("")

    assert capsys.readouterr().out == ""
