"""Acknowledge a portable update only after the Qt event loop can run."""
from __future__ import annotations

import os
from pathlib import Path


def schedule_update_healthcheck() -> None:
    """Keep updater imports and timers out of ordinary and source launches."""
    root = os.environ.get("YAYU_PORTABLE_ROOT")
    if not root or not os.environ.get("YAYU_UPDATE_TOKEN"):
        return

    from PySide6.QtCore import QTimer
    from core.updates.installer import mark_startup_healthy
    from threading import Thread

    # Reaching show() alone does not establish that the event loop runs. Give
    # queued startup work a turn before allowing the installer to commit.
    QTimer.singleShot(1000, lambda: Thread(
        target=mark_startup_healthy, args=(Path(root),),
        name="yayu-update-health", daemon=True,
    ).start())
