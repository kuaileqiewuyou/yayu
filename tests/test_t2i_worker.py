from queue import Empty, Queue

from core.runtime.t2i_worker import T2IWorker


class FakeSignal:
    def __init__(self):
        self.emitted = []

    def emit(self, *args):
        self.emitted.append(args)


class FakeT2IManager:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.prompts = []

    def generate_image(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.result


def make_worker(manager):
    queue = Queue()
    worker = T2IWorker(queue, manager)
    worker.image_generated = FakeSignal()
    worker.generation_failed = FakeSignal()
    return worker, queue


def test_t2i_worker_dispatch_emits_generated_image_path():
    manager = FakeT2IManager(result="data/cg/sunset.png")
    worker, _ = make_worker(manager)

    worker._dispatch("夕阳下的教室")

    assert manager.prompts == ["夕阳下的教室"]
    assert worker.image_generated.emitted == [("data/cg/sunset.png",)]
    assert worker.generation_failed.emitted == []


def test_t2i_worker_emits_comfyui_prompt_handle_as_generated_result():
    manager = FakeT2IManager(result="comfyui://prompt/abc123")
    worker, _ = make_worker(manager)

    worker._dispatch("夕阳下的教室")

    assert worker.image_generated.emitted == [("comfyui://prompt/abc123",)]
    assert worker.generation_failed.emitted == []


def test_t2i_worker_emits_comfyui_image_handle_as_generated_result():
    manager = FakeT2IManager(result="comfyui://image/abc123/galgame_agent_00001_.png")
    worker, _ = make_worker(manager)

    worker._dispatch("夕阳下的教室")

    assert worker.image_generated.emitted == [("comfyui://image/abc123/galgame_agent_00001_.png",)]
    assert worker.generation_failed.emitted == []


def test_t2i_worker_emits_local_cached_image_path_as_generated_result():
    manager = FakeT2IManager(result="data/cg/generated/abc123-galgame_agent_00001_.png")
    worker, _ = make_worker(manager)

    worker._dispatch("夕阳下的教室")

    assert worker.image_generated.emitted == [("data/cg/generated/abc123-galgame_agent_00001_.png",)]
    assert worker.generation_failed.emitted == []


def test_t2i_worker_dispatch_reports_missing_image():
    manager = FakeT2IManager(result=None)
    worker, _ = make_worker(manager)

    worker._dispatch("夕阳下的教室")

    assert manager.prompts == ["夕阳下的教室"]
    assert worker.image_generated.emitted == []
    assert worker.generation_failed.emitted == [("CG 生成未返回图片",)]


def test_t2i_worker_dispatch_reports_generation_exception():
    manager = FakeT2IManager(error=RuntimeError("boom"))
    worker, _ = make_worker(manager)

    worker._dispatch("夕阳下的教室")

    assert manager.prompts == ["夕阳下的教室"]
    assert worker.image_generated.emitted == []
    assert worker.generation_failed.emitted == [("CG 生成失败：boom",)]


def test_t2i_worker_run_consumes_prompt_from_queue_and_exits_when_stopped():
    manager = FakeT2IManager(result="data/cg/classroom.png")
    worker, queue = make_worker(manager)

    original_generate_image = manager.generate_image

    def generate_image_and_stop(prompt):
        result = original_generate_image(prompt)
        worker.stop()
        return result

    manager.generate_image = generate_image_and_stop
    queue.put("教室里的少女")

    worker.run()

    assert manager.prompts == ["教室里的少女"]
    assert worker.image_generated.emitted == [("data/cg/classroom.png",)]


def test_t2i_worker_stop_sets_running_false():
    manager = FakeT2IManager(result="data/cg/classroom.png")
    worker, _ = make_worker(manager)

    worker.stop()

    assert worker._running is False


def test_t2i_worker_run_empty_queue_can_stop_without_dispatching():
    class StopAfterEmptyQueue:
        def __init__(self):
            self.worker = None

        def get(self, timeout):
            self.worker.stop()
            raise Empty

    manager = FakeT2IManager(result="data/cg/unused.png")
    queue = StopAfterEmptyQueue()
    worker = T2IWorker(queue, manager)
    queue.worker = worker
    worker.image_generated = FakeSignal()
    worker.generation_failed = FakeSignal()

    worker.run()

    assert manager.prompts == []
    assert worker.image_generated.emitted == []
    assert worker.generation_failed.emitted == []
