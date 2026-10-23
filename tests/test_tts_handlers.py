from queue import Queue
from types import SimpleNamespace

import pytest

from core.handlers.tts_handlers import DefaultCharacterTtsHandler, NarrTtsHandler
from core.runtime.app_runtime import AppRuntime, set_app_runtime
from core.runtime.cancellation import TurnCancelled, TurnToken, turn_scope
from sdk.messages import LLMDialogMessage


class FailingTTSManager:
    def synthesize(self, text):
        raise RuntimeError("boom")


def test_default_character_tts_handler_emits_error_message_when_synthesis_fails(capsys):
    audio_path_queue = Queue()
    set_app_runtime(AppRuntime(
        config=None,
        llm_manager=None,
        tts_manager=FailingTTSManager(),
        audio_path_queue=audio_path_queue,
    ))
    msg = LLMDialogMessage(name="诺艾尔", text="你好", asset_id="1")

    DefaultCharacterTtsHandler().handle(msg)

    out = audio_path_queue.get_nowait()
    assert out.audio_path == ""
    assert out.name == "诺艾尔"
    assert out.text == "你好"
    assert out.error == "语音合成失败：boom"
    assert out.is_system_message is False
    assert "[TTS] 语音合成失败：boom" in capsys.readouterr().out


class RecordingTTSManager:
    def __init__(self):
        self.calls = []

    def synthesize(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return "voice.wav"


class CharacterConfig:
    def get_character_by_name(self, name):
        assert name == "Noelle"
        return SimpleNamespace(
            refer_audio_path="reference.wav",
            prompt_text="reference text",
            prompt_lang="zh",
            speech_speed=1.1,
        )


def test_default_character_tts_handler_passes_character_voice_settings():
    audio_path_queue = Queue()
    manager = RecordingTTSManager()
    set_app_runtime(AppRuntime(
        config=CharacterConfig(),
        llm_manager=None,
        tts_manager=manager,
        audio_path_queue=audio_path_queue,
    ))
    msg = LLMDialogMessage(name="Noelle", text="hello", asset_id="1")

    DefaultCharacterTtsHandler().handle(msg)

    assert manager.calls == [("hello", {
        "ref_audio_path": "reference.wav",
        "prompt_text": "reference text",
        "prompt_lang": "zh",
        "speed": 1.1,
    })]
    assert audio_path_queue.get_nowait().audio_path == "voice.wav"


def test_default_character_tts_handler_uses_selected_id_for_same_name_characters():
    first = SimpleNamespace(memory_id="first", name="小芽", refer_audio_path="first.wav",
                            prompt_text="第一位角色", prompt_lang="ja", speech_speed=0.8)
    selected = SimpleNamespace(memory_id="selected", name="小芽", refer_audio_path="selected.wav",
                               prompt_text="选中的角色", prompt_lang="zh", speech_speed=1.2)

    def unexpected_name_lookup(_name):
        pytest.fail("An active character must be resolved by stable ID before name lookup")

    manager = RecordingTTSManager()
    output_queue = Queue()
    set_app_runtime(AppRuntime(
        config=SimpleNamespace(characters=[first, selected],
                               system_config=SimpleNamespace(active_character_id="selected"),
                               get_character_by_name=unexpected_name_lookup),
        llm_manager=None, tts_manager=manager, audio_path_queue=output_queue,
    ))

    DefaultCharacterTtsHandler().handle(LLMDialogMessage(name="小芽", text="你好", asset_id="1"))

    assert manager.calls == [("你好", {
        "ref_audio_path": "selected.wav", "prompt_text": "选中的角色",
        "prompt_lang": "zh", "speed": 1.2,
    })]
    assert output_queue.get_nowait().audio_path == "voice.wav"


def test_default_character_tts_handler_discards_audio_completed_after_cancellation():
    token = TurnToken("old-character-session")
    output_queue = Queue()

    class CancelledTTSManager:
        def synthesize(self, text):
            token.cancel()
            return "old-character.wav"

    set_app_runtime(AppRuntime(config=None, llm_manager=None, tts_manager=CancelledTTSManager(),
                               audio_path_queue=output_queue))

    with pytest.raises(TurnCancelled), turn_scope(token):
        DefaultCharacterTtsHandler().handle(LLMDialogMessage(name="旧角色", text="你好", asset_id="1"))

    assert output_queue.empty()


def test_narration_tts_handler_does_not_use_selected_character_voice():
    manager = RecordingTTSManager()
    output_queue = Queue()
    set_app_runtime(AppRuntime(config=None, llm_manager=None, tts_manager=manager,
                               audio_path_queue=output_queue))

    NarrTtsHandler().handle(LLMDialogMessage(name="NARR", text="风吹过树梢。", asset_id="-1"))

    assert manager.calls == []
    narration = output_queue.get_nowait()
    assert narration.name == "NARR"
    assert narration.audio_path == ""
    assert narration.is_system_message is True
