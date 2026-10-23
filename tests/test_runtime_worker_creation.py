from queue import Queue
from types import SimpleNamespace

from core.runtime.llm_worker import LLMWorker
from core.runtime.tts_worker import TTSWorker
from core.runtime.workers import LLMWorker as CompatLLMWorker
from core.runtime.workers import TTSWorker as CompatTTSWorker
from core.runtime.worker_lifecycle import RuntimeWorkers, create_runtime_workers


def make_runtime_setup():
    return SimpleNamespace(
        user_input_queue=Queue(),
        tts_queue=Queue(),
        audio_path_queue=Queue(),
        t2i_prompt_queue=Queue(),
    )


def test_create_runtime_workers_constructs_workers_with_runtime_setup_queues(monkeypatch):
    constructed = []

    class FakeLLMWorker:
        pass

    class FakeTTSWorker:
        pass

    class FakeUIWorker:
        pass

    def make_factory(worker_type):
        def factory(*queues):
            worker = worker_type()
            constructed.append((worker_type.__name__, queues, worker))
            return worker

        return factory

    monkeypatch.setattr("core.runtime.worker_lifecycle.LLMWorker", make_factory(FakeLLMWorker))
    monkeypatch.setattr("core.runtime.worker_lifecycle.TTSWorker", make_factory(FakeTTSWorker))
    monkeypatch.setattr("core.runtime.worker_lifecycle.UIWorker", make_factory(FakeUIWorker))

    user_input_queue = object()
    tts_queue = object()
    audio_path_queue = object()
    runtime_setup = SimpleNamespace(
        user_input_queue=user_input_queue,
        tts_queue=tts_queue,
        audio_path_queue=audio_path_queue,
        t2i_prompt_queue=object(),
    )

    workers = create_runtime_workers(runtime_setup)

    assert isinstance(workers, RuntimeWorkers)
    assert constructed == [
        ("FakeLLMWorker", (user_input_queue, tts_queue), workers.llm_worker),
        ("FakeTTSWorker", (tts_queue, audio_path_queue), workers.tts_worker),
        ("FakeUIWorker", (audio_path_queue,), workers.ui_worker),
    ]


def test_create_runtime_workers_leaves_t2i_worker_none_when_manager_missing():
    setup = make_runtime_setup()

    workers = create_runtime_workers(setup, t2i_manager=None)

    assert workers.t2i_worker is None


def test_create_runtime_workers_creates_t2i_worker_when_manager_present(monkeypatch):
    import core.runtime.worker_lifecycle as worker_lifecycle

    created = []

    class FakeT2IWorker:
        def __init__(self, queue, manager):
            self.queue = queue
            self.manager = manager
            created.append(self)

    monkeypatch.setattr(worker_lifecycle, "T2IWorker", FakeT2IWorker)
    setup = make_runtime_setup()
    manager = object()

    workers = create_runtime_workers(setup, t2i_manager=manager)

    assert workers.t2i_worker is created[0]
    assert workers.t2i_worker.queue is setup.t2i_prompt_queue
    assert workers.t2i_worker.manager is manager


def test_llm_worker_compatibility_export_is_extracted_class():
    assert CompatLLMWorker is LLMWorker


def test_tts_worker_compatibility_export_is_extracted_class():
    assert CompatTTSWorker is TTSWorker
