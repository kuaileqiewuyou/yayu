"""Independent regressions for upgrade boundaries; all profiles are synthetic."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from core.updates import installer


def _write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def _metadata(name, body):
    return {"path": name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def _plan(tmp_path):
    root = tmp_path / "portable"
    root.mkdir()
    token = "a" * 32
    work = tmp_path / ".yayu-updates" / token
    stage = work / "stage"
    stage.mkdir(parents=True)
    files = {name: ("old " + name).encode() for name in installer.REQUIRED | {"main.py"}}
    files["VERSION"] = b"1.0.3"
    files[installer.BUILD_INFO] = b'{"version":"1.0.3"}'
    old = {name: _metadata(name, body) for name, body in sorted(files.items())}
    for name, body in files.items():
        _write(root / name, body)
        _write(stage / name, body)
    _write(root / installer.MANIFEST, json.dumps(list(old.values())).encode())
    _write(stage / installer.MANIFEST, json.dumps(list(old.values())).encode())
    _write(root / "data/config/api.local.yaml", b"synthetic private configuration")
    _write(root / "data/chat_history/sessions.json", b"synthetic private sessions")
    plan = {
        "schema_version": 1, "token": token, "app_root": str(root), "work_dir": str(work),
        "stage_dir": str(stage), "backup_dir": str(work / "backup"), "version": "1.0.4",
        "old_files": old, "new_files": copy.deepcopy(old), "restart_exe": "Yayu.exe",
        "recovery_python": str(work / "worker-runtime/python.exe"),
        "recovery_script": str(work / "installer.py"), "wait_timeout": 1, "health_timeout": 1,
    }
    return plan


def _store_plan(plan):
    path = Path(plan["work_dir"]) / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


@pytest.mark.parametrize("field", ["old_files", "new_files"])
@pytest.mark.parametrize("name", [
    "DATA/config/api.local.yaml", "Data/chat_history/sessions.json",
    "data/chat_history/sessions.json", "logs/chat.log", "user-notes.txt",
])
def test_recovery_plan_revalidates_private_and_unmanaged_path_boundaries(tmp_path, field, name):
    plan = _plan(tmp_path)
    plan[field][name] = _metadata(name, b"untrusted")
    with pytest.raises(installer.UpdateError):
        installer._load_plan(_store_plan(plan))
    root = Path(plan["app_root"])
    assert (root / "data/config/api.local.yaml").read_bytes() == b"synthetic private configuration"
    assert (root / "data/chat_history/sessions.json").read_bytes() == b"synthetic private sessions"


@pytest.mark.parametrize("metadata_change", [
    {"bytes": True}, {"bytes": -1}, {"sha256": "broken"}, {"path": "data/chat_history/sessions.json"},
])
def test_recovery_plan_revalidates_metadata_not_only_relative_paths(tmp_path, metadata_change):
    plan = _plan(tmp_path)
    plan["new_files"]["main.py"].update(metadata_change)
    with pytest.raises(installer.UpdateError):
        installer._load_plan(_store_plan(plan))


@pytest.mark.parametrize("relative", [
    "data/config/api.local.yaml", "DATA/config/api.local.yaml", "Data/chat_history/sessions.json",
    "logs/chat.log", ".yayu-app.lock", ".YAYU-update-pending.json",
])
def test_remove_entrypoint_independently_protects_private_paths_and_locks(tmp_path, relative):
    with pytest.raises(installer.UpdateError):
        installer._remove_file(tmp_path, relative)


@pytest.mark.parametrize("contamination", ["user-notes.txt", "data/config/api.local.yaml", "DATA/config/api.local.yaml"])
def test_rollback_does_not_restore_arbitrary_unlisted_backup_contents(tmp_path, contamination):
    plan = _plan(tmp_path)
    root = Path(plan["app_root"])
    _write(root / "user-notes.txt", b"synthetic user document")
    installer._copy_backup(plan)
    managed = Path(plan["backup_dir"]) / "managed"
    _write(managed / contamination, b"unlisted backup content")
    try:
        installer._rollback(plan)
    except installer.UpdateError:
        # Refusing a contaminated backup is also safe; never restore it blindly.
        pass
    assert (root / "user-notes.txt").read_bytes() == b"synthetic user document"
    assert (root / "data/config/api.local.yaml").read_bytes() == b"synthetic private configuration"


def test_failed_rollback_copy_does_not_truncate_the_live_launcher(tmp_path, monkeypatch):
    plan = _plan(tmp_path)
    root = Path(plan["app_root"])
    installer._copy_backup(plan)
    launcher = root / "Yayu.exe"
    launcher.write_bytes(b"still usable launcher")
    real_copy = installer.shutil.copy2

    def interrupted_copy(source, destination, *args, **kwargs):
        if Path(source).name == "Yayu.exe":
            Path(destination).write_bytes(b"partial")
            raise OSError("synthetic interruption during rollback")
        return real_copy(source, destination, *args, **kwargs)

    monkeypatch.setattr(installer.shutil, "copy2", interrupted_copy)
    with pytest.raises(OSError, match="synthetic interruption"):
        installer._rollback(plan)
    assert launcher.read_bytes() == b"still usable launcher"
