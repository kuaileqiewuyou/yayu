"""Startup acknowledgement requires an actual event-loop turn, not an import."""
from pathlib import Path

from core.runtime.update_lifecycle import schedule_update_healthcheck


def test_source_and_ordinary_launches_do_not_import_update_engine(monkeypatch):
    import sys
    from PySide6.QtCore import QTimer

    monkeypatch.delenv("YAYU_PORTABLE_ROOT", raising=False)
    monkeypatch.delenv("YAYU_UPDATE_TOKEN", raising=False)
    monkeypatch.setattr(QTimer, "singleShot", lambda *_: (_ for _ in ()).throw(AssertionError("unexpected timer")))
    before = sys.modules.get("core.updates.installer")
    schedule_update_healthcheck()
    monkeypatch.setenv("YAYU_PORTABLE_ROOT", "unused-root")
    schedule_update_healthcheck()
    assert sys.modules.get("core.updates.installer") is before


def test_updated_portable_launch_is_acknowledged_after_event_loop_turn(tmp_path, monkeypatch):
    import threading
    from PySide6.QtCore import QTimer
    from core.updates import installer

    calls = []
    timers = []
    threads = []

    class FakeThread:
        def __init__(self, *, target, args, name, daemon):
            self.target, self.args = target, args
            threads.append((name, daemon))

        def start(self):
            self.target(*self.args)

    monkeypatch.setenv("YAYU_PORTABLE_ROOT", str(tmp_path))
    monkeypatch.setenv("YAYU_UPDATE_TOKEN", "test-update-token")
    monkeypatch.setattr(installer, "mark_startup_healthy", lambda root: calls.append(root))
    monkeypatch.setattr(threading, "Thread", FakeThread)
    monkeypatch.setattr(QTimer, "singleShot", lambda delay, callback: timers.append((delay, callback)))
    schedule_update_healthcheck()
    assert calls == []
    assert len(timers) == 1 and timers[0][0] == 1000
    timers[0][1]()
    assert calls == [Path(tmp_path)]
    assert threads == [("yayu-update-health", True)]
