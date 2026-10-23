import os

import pytest

from config.atomic_io import atomic_write_text


def test_atomic_write_text_replaces_target_and_fsyncs(tmp_path, monkeypatch):
    target = tmp_path / "config.yaml"
    target.write_text("old", encoding="utf-8")
    fsync_calls = []
    real_fsync = os.fsync

    def tracked_fsync(fd):
        fsync_calls.append(fd)
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", tracked_fsync)

    atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "new"
    assert fsync_calls
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_text_preserves_target_and_cleans_temp_when_replace_fails(tmp_path, monkeypatch):
    target = tmp_path / "config.yaml"
    target.write_text("old", encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob("*.tmp")) == []
