"""Runtime worker creation and lifecycle helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

from core.runtime.t2i_worker import T2IWorker
from core.runtime.tts_worker import TTSWorker
from core.runtime.ui_worker import UIWorker
from core.runtime.llm_worker import LLMWorker
from core.runtime.runtime_lifecycle import run_runtime_event_loop

WORKER_STOP_WAIT_TIMEOUT_MS = 1000

if TYPE_CHECKING:
    from core.runtime.runtime_setup import RuntimeSetup


@dataclass(frozen=True)
class RuntimeWorkerFailure:
    phase: str
    worker_name: str
    error: BaseException


class RuntimeWorkersStopError(RuntimeError):
    def __init__(self, failures: Sequence[RuntimeWorkerFailure]):
        self.failures = tuple(failures)
        details = "; ".join(
            f"{failure.phase} {failure.worker_name} {type(failure.error).__name__}"
            for failure in self.failures
        )
        super().__init__(
            f"Failed to stop {len(self.failures)} runtime worker operation(s): {details}"
        )


@dataclass
class RuntimeWorkers:
    llm_worker: LLMWorker
    tts_worker: TTSWorker
    ui_worker: UIWorker
    t2i_worker: T2IWorker | None = None

    def _iter_workers(self):
        yield "llm_worker", self.llm_worker
        yield "tts_worker", self.tts_worker
        yield "ui_worker", self.ui_worker
        if self.t2i_worker is not None:
            yield "t2i_worker", self.t2i_worker

    def start_all(self) -> None:
        for _, worker in self._iter_workers():
            worker.start()

    def stop_all(self) -> None:
        failures: list[RuntimeWorkerFailure] = []
        workers = list(self._iter_workers())

        for worker_name, worker in workers:
            try:
                worker.stop()
            except Exception as exc:
                failures.append(RuntimeWorkerFailure("stop", worker_name, exc))

        for worker_name, worker in workers:
            try:
                self._wait_for_worker(worker)
            except Exception as exc:
                failures.append(RuntimeWorkerFailure("wait", worker_name, exc))

        if failures:
            raise RuntimeWorkersStopError(failures)

    @staticmethod
    def _wait_for_worker(worker, timeout_ms: int = WORKER_STOP_WAIT_TIMEOUT_MS) -> None:
        wait = getattr(worker, "wait", None)
        if callable(wait):
            if wait(timeout_ms) is False:
                raise TimeoutError(f"Worker is still running after {timeout_ms} ms")


def create_runtime_workers(runtime_setup: "RuntimeSetup", t2i_manager=None) -> RuntimeWorkers:
    t2i_worker = None
    if t2i_manager is not None:
        t2i_worker = T2IWorker(runtime_setup.t2i_prompt_queue, t2i_manager)

    return RuntimeWorkers(
        llm_worker=LLMWorker(runtime_setup.user_input_queue, runtime_setup.tts_queue),
        tts_worker=TTSWorker(runtime_setup.tts_queue, runtime_setup.audio_path_queue),
        ui_worker=UIWorker(runtime_setup.audio_path_queue),
        t2i_worker=t2i_worker,
    )
