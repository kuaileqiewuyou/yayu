from queue import Queue

from core.runtime.tts_worker import TTSWorker
from sdk.messages import LLMDialogMessage


class RecordingHandler:
    def __init__(self, name, can_handle_result, calls):
        self.name = name
        self.can_handle_result = can_handle_result
        self.calls = calls

    def can_handle(self, msg):
        self.calls.append((self.name, "can_handle", msg))
        return self.can_handle_result

    def pre_process(self, msg):
        self.calls.append((self.name, "pre_process", msg))

    def handle(self, msg):
        self.calls.append((self.name, "handle", msg))

    def post_process(self, msg):
        self.calls.append((self.name, "post_process", msg))


def make_worker(handlers):
    worker = TTSWorker(Queue(), Queue())
    worker._handlers = handlers
    return worker


def make_message():
    return LLMDialogMessage(name="角色", text="你好", asset_id="-1")


def test_tts_worker_dispatch_runs_first_matching_handler_chain_and_stops():
    calls = []
    msg = make_message()
    first = RecordingHandler("first", False, calls)
    second = RecordingHandler("second", True, calls)
    third = RecordingHandler("third", True, calls)
    worker = make_worker([first, second, third])

    worker._dispatch(msg)

    assert calls == [
        ("first", "can_handle", msg),
        ("second", "can_handle", msg),
        ("second", "pre_process", msg),
        ("second", "handle", msg),
        ("second", "post_process", msg),
    ]


def test_tts_worker_dispatch_does_not_run_chain_for_non_matching_handlers():
    calls = []
    msg = make_message()
    first = RecordingHandler("first", False, calls)
    second = RecordingHandler("second", False, calls)
    worker = make_worker([first, second])

    worker._dispatch(msg)

    assert calls == [
        ("first", "can_handle", msg),
        ("second", "can_handle", msg),
    ]
