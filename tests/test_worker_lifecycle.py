import pytest

from core.runtime import runtime_lifecycle, worker_lifecycle
from core.runtime.worker_lifecycle import RuntimeWorkers


class FakeWorker:
    def __init__(
        self,
        name,
        events,
        *,
        start_error=None,
        stop_error=None,
        wait_error=None,
        wait_result=True,
    ):
        self.name = name
        self.events = events
        self.start_error = start_error
        self.stop_error = stop_error
        self.wait_error = wait_error
        self.wait_result = wait_result

    def start(self):
        self.events.append(f"start {self.name}")
        if self.start_error is not None:
            raise self.start_error

    def stop(self):
        self.events.append(f"stop {self.name}")
        if self.stop_error is not None:
            raise self.stop_error

    def wait(self, timeout_ms):
        self.events.append(f"wait {self.name} {timeout_ms}")
        if self.wait_error is not None:
            raise self.wait_error
        return self.wait_result


class FakeWorkerWithoutWait:
    def __init__(self, name, events):
        self.name = name
        self.events = events

    def start(self):
        self.events.append(f"start {self.name}")

    def stop(self):
        self.events.append(f"stop {self.name}")


def make_workers(events, *, t2i=True, **overrides):
    workers = {
        "llm_worker": FakeWorker("llm_worker", events),
        "tts_worker": FakeWorker("tts_worker", events),
        "ui_worker": FakeWorker("ui_worker", events),
        "t2i_worker": FakeWorker("t2i_worker", events) if t2i else None,
    }
    workers.update(overrides)
    return RuntimeWorkers(**workers)


def test_start_all_starts_workers_in_order_with_t2i():
    events = []
    workers = make_workers(events)

    workers.start_all()

    assert events == [
        "start llm_worker",
        "start tts_worker",
        "start ui_worker",
        "start t2i_worker",
    ]


def test_start_all_starts_workers_in_order_without_t2i():
    events = []
    workers = make_workers(events, t2i=False)

    workers.start_all()

    assert events == [
        "start llm_worker",
        "start tts_worker",
        "start ui_worker",
    ]


def test_stop_all_stops_all_workers_then_waits_in_order_with_t2i():
    events = []
    workers = make_workers(events)

    workers.stop_all()

    assert events == [
        "stop llm_worker",
        "stop tts_worker",
        "stop ui_worker",
        "stop t2i_worker",
        "wait llm_worker 1000",
        "wait tts_worker 1000",
        "wait ui_worker 1000",
        "wait t2i_worker 1000",
    ]


def test_stop_all_stops_and_waits_in_order_without_t2i():
    events = []
    workers = make_workers(events, t2i=False)

    workers.stop_all()

    assert events == [
        "stop llm_worker",
        "stop tts_worker",
        "stop ui_worker",
        "wait llm_worker 1000",
        "wait tts_worker 1000",
        "wait ui_worker 1000",
    ]


def test_wait_for_worker_ignores_worker_without_callable_wait():
    events = []
    worker_without_wait = FakeWorkerWithoutWait("ui_worker", events)
    workers = make_workers(events, t2i=False, ui_worker=worker_without_wait)

    workers.stop_all()

    assert events == [
        "stop llm_worker",
        "stop tts_worker",
        "stop ui_worker",
        "wait llm_worker 1000",
        "wait tts_worker 1000",
    ]


def test_stop_all_continues_after_stop_exception_and_reports_failure():
    from core.runtime.worker_lifecycle import RuntimeWorkersStopError

    events = []
    stop_error = RuntimeError("llm stop failed")
    workers = make_workers(
        events,
        llm_worker=FakeWorker("llm_worker", events, stop_error=stop_error),
    )

    with pytest.raises(RuntimeWorkersStopError) as exc_info:
        workers.stop_all()

    assert events == [
        "stop llm_worker",
        "stop tts_worker",
        "stop ui_worker",
        "stop t2i_worker",
        "wait llm_worker 1000",
        "wait tts_worker 1000",
        "wait ui_worker 1000",
        "wait t2i_worker 1000",
    ]
    assert len(exc_info.value.failures) == 1
    failure = exc_info.value.failures[0]
    assert failure.phase == "stop"
    assert failure.worker_name == "llm_worker"
    assert failure.error is stop_error


def test_stop_all_continues_after_wait_exception_and_reports_failure():
    from core.runtime.worker_lifecycle import RuntimeWorkersStopError

    events = []
    wait_error = TimeoutError("ui wait failed")
    workers = make_workers(
        events,
        ui_worker=FakeWorker("ui_worker", events, wait_error=wait_error),
    )

    with pytest.raises(RuntimeWorkersStopError) as exc_info:
        workers.stop_all()

    assert events == [
        "stop llm_worker",
        "stop tts_worker",
        "stop ui_worker",
        "stop t2i_worker",
        "wait llm_worker 1000",
        "wait tts_worker 1000",
        "wait ui_worker 1000",
        "wait t2i_worker 1000",
    ]
    assert len(exc_info.value.failures) == 1
    failure = exc_info.value.failures[0]
    assert failure.phase == "wait"
    assert failure.worker_name == "ui_worker"
    assert failure.error is wait_error


def test_stop_error_exposes_multiple_failures_and_readable_message():
    from core.runtime.worker_lifecycle import RuntimeWorkersStopError

    events = []
    stop_error = RuntimeError("llm stop failed")
    wait_error = TimeoutError("ui wait failed")
    workers = make_workers(
        events,
        llm_worker=FakeWorker("llm_worker", events, stop_error=stop_error),
        ui_worker=FakeWorker("ui_worker", events, wait_error=wait_error),
    )

    with pytest.raises(RuntimeWorkersStopError) as exc_info:
        workers.stop_all()

    failures = exc_info.value.failures
    assert len(failures) == 2
    assert failures[0].phase == "stop"
    assert failures[0].worker_name == "llm_worker"
    assert failures[0].error is stop_error
    assert failures[1].phase == "wait"
    assert failures[1].worker_name == "ui_worker"
    assert failures[1].error is wait_error

    message = str(exc_info.value)
    assert "Failed to stop 2 runtime worker operation(s)" in message
    assert "stop llm_worker RuntimeError" in message
    assert "wait ui_worker TimeoutError" in message


@pytest.mark.parametrize("control_flow_error", [KeyboardInterrupt(), SystemExit(2)])
def test_stop_all_does_not_wrap_control_flow_stop_exceptions(control_flow_error):
    events = []
    workers = make_workers(
        events,
        llm_worker=FakeWorker("llm_worker", events, stop_error=control_flow_error),
    )

    with pytest.raises(type(control_flow_error)):
        workers.stop_all()

    assert events == ["stop llm_worker"]


@pytest.mark.parametrize("control_flow_error", [KeyboardInterrupt(), SystemExit(2)])
def test_stop_all_does_not_wrap_control_flow_wait_exceptions(control_flow_error):
    events = []
    workers = make_workers(
        events,
        llm_worker=FakeWorker("llm_worker", events, wait_error=control_flow_error),
    )

    with pytest.raises(type(control_flow_error)):
        workers.stop_all()

    assert events == [
        "stop llm_worker",
        "stop tts_worker",
        "stop ui_worker",
        "stop t2i_worker",
        "wait llm_worker 1000",
    ]


def test_start_all_keeps_fail_fast_startup_semantics():
    events = []
    start_error = RuntimeError("tts start failed")
    workers = make_workers(
        events,
        tts_worker=FakeWorker("tts_worker", events, start_error=start_error),
    )

    with pytest.raises(RuntimeError) as exc_info:
        workers.start_all()

    assert exc_info.value is start_error
    assert events == [
        "start llm_worker",
        "start tts_worker",
    ]


def test_false_wait_return_value_reports_worker_still_running():
    events = []
    workers = make_workers(
        events,
        ui_worker=FakeWorker("ui_worker", events, wait_result=False),
    )

    with pytest.raises(worker_lifecycle.RuntimeWorkersStopError) as error:
        workers.stop_all()
    assert isinstance(error.value.failures[0].error, TimeoutError)

    assert events == [
        "stop llm_worker",
        "stop tts_worker",
        "stop ui_worker",
        "stop t2i_worker",
        "wait llm_worker 1000",
        "wait tts_worker 1000",
        "wait ui_worker 1000",
        "wait t2i_worker 1000",
    ]


def test_worker_lifecycle_run_runtime_event_loop_is_compatibility_re_export():
    assert worker_lifecycle.run_runtime_event_loop is runtime_lifecycle.run_runtime_event_loop
