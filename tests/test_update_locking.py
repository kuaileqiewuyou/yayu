import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from core.updates.locking import APP_LOCK, PENDING_MARKER, FileLock, UpdateInProgressError, application_lock, update_lock


def test_multiple_running_apps_share_lifetime_lock(tmp_path):
    with application_lock(tmp_path), application_lock(tmp_path):
        with pytest.raises(TimeoutError):
            update_lock(tmp_path, timeout=0).acquire()
    with update_lock(tmp_path, timeout=0):
        with pytest.raises(TimeoutError):
            application_lock(tmp_path, timeout=0).acquire()


def test_application_lock_released_after_exception(tmp_path):
    with pytest.raises(RuntimeError):
        with application_lock(tmp_path):
            raise RuntimeError("fixture")
    with update_lock(tmp_path, timeout=0):
        pass


def test_pending_update_blocks_ordinary_start_but_allows_token_restart(tmp_path, monkeypatch):
    (tmp_path / PENDING_MARKER).write_text(json.dumps({"token": "fixture-token"}))
    monkeypatch.delenv("YAYU_UPDATE_TOKEN", raising=False)
    with pytest.raises(UpdateInProgressError):
        application_lock(tmp_path).acquire()
    # Failure must close the shared handle as well.
    with update_lock(tmp_path, timeout=0):
        pass
    monkeypatch.setenv("YAYU_UPDATE_TOKEN", "fixture-token")
    with application_lock(tmp_path):
        pass


def test_corrupt_pending_marker_fails_closed(tmp_path):
    (tmp_path / PENDING_MARKER).write_text("not json")
    with pytest.raises(UpdateInProgressError):
        application_lock(tmp_path).acquire()


def test_shared_lock_blocks_separate_process_update(tmp_path):
    code = "from pathlib import Path; from core.updates.locking import update_lock; update_lock(Path(__import__('sys').argv[1]), timeout=0).acquire()"
    with application_lock(tmp_path):
        result = subprocess.run([sys.executable, "-c", code, str(tmp_path)], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode != 0
    assert "TimeoutError" in result.stderr
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path)], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_lock_file_inode_is_not_deleted_when_released(tmp_path):
    with application_lock(tmp_path):
        inode = (tmp_path / APP_LOCK).stat().st_ino
    with update_lock(tmp_path, timeout=0):
        assert (tmp_path / APP_LOCK).stat().st_ino == inode
