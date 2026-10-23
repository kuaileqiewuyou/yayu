from queue import Queue
from types import SimpleNamespace

import pytest

from core.runtime.cancellation import TurnEvent, TurnToken, TurnWork
from core.runtime.turn_controller import TurnController
from core.runtime.ui_worker import UIWorker
from core.runtime.workers import UIWorker as CompatUIWorker
from sdk.messages import TTSOutputMessage


def test_ui_worker_compatibility_export_is_extracted_class():
    assert CompatUIWorker is UIWorker


def test_ui_worker_dispatch_emits_choice_options():
    worker = UIWorker(Queue())
    emitted = []
    worker.update_options.connect(lambda options: emitted.append(options))

    worker._dispatch(TTSOutputMessage(name="CHOICE", text="继续 / 离开 / 休息", asset_id="-1"))

    assert emitted == [["继续", "离开", "休息"]]


@pytest.mark.parametrize("name", ["SCENE", "scene", "场景", "BGM", "bgm", "BgM"])
def test_ui_worker_dispatch_ignores_legacy_scene_and_music_for_both_queue_formats(name):
    worker = UIWorker(Queue())
    dialogs = []
    turn_events = []
    worker.update_dialog.connect(dialogs.append)
    worker.turn_event.connect(turn_events.append)
    output = TTSOutputMessage(name=name, text="旧控制消息", asset_id="2", audio_path="unused.ogg")

    worker._dispatch(output)
    worker._dispatch(TurnWork(TurnToken("test-session"), output))

    assert dialogs == []
    assert turn_events == []


@pytest.mark.parametrize("kind", ["ui_scene", "ui_bgm"])
def test_turn_controller_ignores_retired_events_already_in_the_queue(kind):
    token = TurnToken("test-session")
    controller = SimpleNamespace(
        closing=False,
        token=token,
        history=SimpleNamespace(get_active_session_id=lambda: "test-session"),
    )

    # No UI handler lookup is permitted for these stale events.
    TurnController.receive(controller, TurnEvent(token, kind, "1"))


def test_ui_worker_dispatch_emits_character_dialog():
    worker = UIWorker(Queue())
    out = TTSOutputMessage(name="诺艾尔", text="欢迎回来。", asset_id="1", audio_path="voice.wav")
    emitted = []
    worker.update_dialog.connect(lambda msg: emitted.append(msg))

    worker._dispatch(out)

    assert emitted == [out]


def test_ui_worker_dispatch_emits_cot_debug_text():
    worker = UIWorker(Queue())
    emitted = []
    worker.update_cot.connect(lambda text: emitted.append(text))

    worker._dispatch(TTSOutputMessage(name="COT", text="内部思考", asset_id="-1"))

    assert emitted == ["内部思考"]
