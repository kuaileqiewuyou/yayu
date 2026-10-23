"""Updater tests use fake distributions/profiles only; never the real data tree."""
import hashlib
import json
import os
from pathlib import Path
import stat
import zipfile

import pytest

from core.updates import installer as engine


def _write(root, relative, content):
    path = engine._fs(root / relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content if isinstance(content, bytes) else content.encode())


def _distribution(root, version, **extra):
    files = {
        "VERSION": version, "BUILD_INFO.json": json.dumps({"version": version, "platform": "windows-x64"}),
        "portable_bootstrap.py": "# fake " + version, "main.py": "# fake main",
        "Yayu.exe": "fake-launcher-" + version, "Yayu Settings.exe": "fake-settings-" + version,
        "runtime/python.exe": "fake-python-" + version, "runtime/python313.zip": "fake-stdlib-" + version,
        "runtime/Lib/site-packages/fake-package.py": version,
        "core/feature.py": version, "data/config/api.yaml": "llm_api_key: {}\n",
        "data/config/api.example.yaml": "llm_api_key: {}\n",
        "data/characters/xiaoya/persona.md": "public starter " + version,
    }
    files.update(extra)
    for name, content in files.items():
        _write(root, name, content)
    manifest = [{"path": name, "bytes": engine._fs(root / name).stat().st_size, "sha256": engine._sha256(root / name)} for name in files]
    _write(root, engine.MANIFEST, json.dumps(manifest))
    return root


def _archive(tmp_path, version="1.0.4", extra=None):
    source = _distribution(tmp_path / ("source-" + version), version, **(extra or {}))
    target = tmp_path / ("new-" + version + ".zip")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in engine._fs(source).rglob("*"):
            if path.is_file():
                archive.write(path, f"Yayu-{version}-windows-x64/" + path.relative_to(engine._fs(source)).as_posix())
    return target


@pytest.fixture
def install(tmp_path):
    root = _distribution(tmp_path / "原版 芽语", "1.0.3", **{"core/removed.py": "obsolete"})
    for name, content in {
        "data/config/api.local.yaml": "fictional-secret-for-test-only",
        "data/config/characters.yaml": "[{name: test, memory_id: fixed-test-id}]",
        "data/config/system_config.yaml": "active_character_id: fixed-test-id",
        "data/chat_history/default.json": "fixture conversation",
        "data/chat_history/sessions.json": "fixture session index",
        "data/chat_history/memory.sqlite3": b"fixture db",
        "data/chat_history/memory.sqlite3-wal": b"fixture WAL",
        "data/chat_history/memory.sqlite3-shm": b"fixture SHM",
        "data/characters/xiaoya/persona.md": "customized old persona",
        "data/custom/user-image.png": b"fixture image",
        "logs/user.log": "keep log",
        "my notes.txt": "keep unrelated root file",
        "core/custom-user.py": "keep unrelated user code",
    }.items():
        _write(root, name, content)
    return root


def _snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _prepare(tmp_path, install, **extra):
    archive = _archive(tmp_path, extra=extra)
    return engine.prepare_update(archive, install, "1.0.4", engine._sha256(archive))


def test_prepare_changes_no_program_or_profile_and_survives_archive_removal(tmp_path, install):
    before = _snapshot(install)
    archive = _archive(tmp_path)
    prepared = engine.prepare_update(archive, install, "1.0.4", engine._sha256(archive))
    archive.unlink()
    after = _snapshot(install)
    assert {k: v for k, v in after.items() if not k.startswith(".yayu-")} == before
    assert prepared.plan_path.is_file()
    assert not prepared.backup_dir.exists()
    assert not prepared.plan_path.is_relative_to(install)
    assert (prepared.plan_path.parent / "worker-runtime/python.exe").is_file()


def test_success_keeps_entire_profile_logs_unmanaged_and_backs_up_closed_data(tmp_path, install, monkeypatch):
    before = _snapshot(install / "data")
    prepared = _prepare(tmp_path, install, **{"core/added.py": "new feature"})
    monkeypatch.setattr(engine, "_restart", lambda plan: object())
    monkeypatch.setattr(engine, "_await_health", lambda plan, process: True)
    assert engine.run_worker(prepared.plan_path) == 0
    assert _snapshot(install / "data") == before
    assert _snapshot(prepared.backup_dir / "data") == before
    assert (install / "VERSION").read_text() == "1.0.4"
    assert not (install / "core/removed.py").exists()
    assert (install / "core/added.py").read_text() == "new feature"
    assert (install / "logs/user.log").read_text() == "keep log"
    assert (install / "my notes.txt").read_text() == "keep unrelated root file"
    assert (install / "core/custom-user.py").read_text() == "keep unrelated user code"
    assert not (install / engine.PENDING_MARKER).exists()
    assert json.loads((prepared.plan_path.parent / "journal.json").read_text())["state"] == "complete"


def test_runtime_replaced_whole_without_old_packages_or_cache(tmp_path, install, monkeypatch):
    _write(install, "runtime/Lib/site-packages/__pycache__/fake-package.cpython-313.pyc", b"generated cache")
    prepared = _prepare(tmp_path, install)
    monkeypatch.setattr(engine, "_restart", lambda plan: object())
    monkeypatch.setattr(engine, "_await_health", lambda *args: True)
    assert engine.run_worker(prepared.plan_path) == 0
    assert not (install / "runtime/Lib/site-packages/__pycache__").exists()
    assert (install / "runtime/Lib/site-packages/fake-package.py").read_text() == "1.0.4"


def test_windows_long_bundled_paths_stage_copy_and_rollback(tmp_path, install, monkeypatch):
    relative = "licenses/qt/upstream/" + "/".join("a-long-upstream-folder" for _ in range(7)) + "/MARKDOWN-LICENSE.txt"
    prepared = _prepare(tmp_path, install, **{relative: "fake upstream license"})
    staged = engine._fs(prepared.plan_path.parent / "stage" / relative)
    assert len(str(staged)) > 260
    assert staged.read_text() == "fake upstream license"
    plan = engine._load_plan(prepared.plan_path)
    engine._copy_backup(plan)
    engine._write_journal(plan, "installing")
    engine._apply_files(plan)
    assert engine._fs(install / relative).read_text() == "fake upstream license"
    engine._rollback(plan)
    assert not engine._fs(install / relative).exists()
    assert (install / "VERSION").read_text() == "1.0.3"


def test_cancelled_late_worker_never_touches_application(tmp_path, install):
    before = _snapshot(install)
    prepared = _prepare(tmp_path, install)
    engine._atomic_json(prepared.plan_path.parent / "cancel.json", {"token": engine._load_plan(prepared.plan_path)["token"]})
    assert engine.run_worker(prepared.plan_path, require_launch_ack=True) == 1
    assert not prepared.backup_dir.exists()
    assert {k: v for k, v in _snapshot(install).items() if not k.startswith(".yayu-")} == before


def test_failed_startup_rolls_back_program_but_never_overwrites_profile(tmp_path, install, monkeypatch):
    before = _snapshot(install)
    prepared = _prepare(tmp_path, install, **{"core/added.py": "new feature"})
    monkeypatch.setattr(engine, "_restart", lambda plan: object())
    monkeypatch.setattr(engine, "_await_health", lambda *args: False)
    monkeypatch.setattr(engine, "_request_close_installation_windows", lambda root: None)
    monkeypatch.setattr(engine, "_notify", lambda *args, **kwargs: None)
    assert engine.run_worker(prepared.plan_path) == 1
    after = _snapshot(install)
    assert {k: v for k, v in after.items() if not k.startswith(".yayu-")} == before
    assert not (install / engine.PENDING_MARKER).exists()


def test_partial_file_copy_failure_rolls_back(tmp_path, install, monkeypatch):
    before = _snapshot(install)
    prepared = _prepare(tmp_path, install)
    real_apply = engine._apply_files

    def fail(plan):
        real_apply(plan)
        raise OSError("fixture disk failure")

    monkeypatch.setattr(engine, "_apply_files", fail)
    monkeypatch.setattr(engine, "_notify", lambda *args, **kwargs: None)
    monkeypatch.setattr(engine, "_restart", lambda plan: object())
    assert engine.run_worker(prepared.plan_path) == 1
    assert {k: v for k, v in _snapshot(install).items() if not k.startswith(".yayu-")} == before


def test_recover_interrupted_runtime_and_file_replacement(tmp_path, install, monkeypatch):
    before = _snapshot(install)
    prepared = _prepare(tmp_path, install)
    plan = engine._load_plan(prepared.plan_path)
    engine._copy_backup(plan)
    engine._write_journal(plan, "installing")
    os.replace(install / "runtime", prepared.plan_path.parent / "old-runtime")
    _write(install, "runtime/python.exe", "interrupted new runtime")
    _write(install, "core/feature.py", "interrupted new feature")
    monkeypatch.setattr(engine, "_notify", lambda *args, **kwargs: None)
    monkeypatch.setattr(engine, "_restart", lambda plan: object())
    assert engine.run_worker(prepared.plan_path, recover=True) == 0
    assert {k: v for k, v in _snapshot(install).items() if not k.startswith(".yayu-")} == before


def test_profile_changes_after_new_startup_are_not_lost_on_rollback(tmp_path, install, monkeypatch):
    prepared = _prepare(tmp_path, install)
    monkeypatch.setattr(engine, "_restart", lambda plan: object())

    def failed_health(*args):
        _write(install, "data/chat_history/default.json", "new user activity survives")
        return False

    monkeypatch.setattr(engine, "_await_health", failed_health)
    monkeypatch.setattr(engine, "_request_close_installation_windows", lambda root: None)
    monkeypatch.setattr(engine, "_notify", lambda *args, **kwargs: None)
    assert engine.run_worker(prepared.plan_path) == 1
    assert (install / "data/chat_history/default.json").read_text() == "new user activity survives"
    assert (prepared.backup_dir / "data/chat_history/default.json").read_text() == "fixture conversation"


@pytest.mark.parametrize("marker", [".git", "venv"])
def test_source_checkout_cannot_self_update(tmp_path, install, marker):
    (install / marker).mkdir()
    assert not engine.is_portable_install(install)
    with pytest.raises(engine.UpdateError, match="源码"):
        _prepare(tmp_path, install)


def test_missing_manifest_not_portable(install):
    (install / engine.MANIFEST).unlink()
    assert not engine.is_portable_install(install)


def test_bad_download_hash_never_creates_pending_or_changes_profile(tmp_path, install):
    before = _snapshot(install)
    archive = _archive(tmp_path)
    with pytest.raises(engine.UpdateError, match="SHA256"):
        engine.prepare_update(archive, install, "1.0.4", "0" * 64)
    assert _snapshot(install) == before


def test_manifest_hash_tampering_is_rejected(tmp_path, install):
    archive = _archive(tmp_path)
    with zipfile.ZipFile(archive, "a") as package:
        package.writestr("Yayu-1.0.4-windows-x64/core/unlisted.py", "injected")
    with pytest.raises(engine.UpdateError, match="清单"):
        engine.prepare_update(archive, install, "1.0.4", engine._sha256(archive))
    assert not (install / engine.PENDING_MARKER).exists()


@pytest.mark.parametrize("name", ["../outside", "/absolute", "a\\b", "C:/ADS", "runtime/file:stream", "runtime/NUL.txt", "runtime/file.", "runtime/file ", "runtime//empty"])
def test_unsafe_zip_paths_rejected(tmp_path, install, name):
    archive = _archive(tmp_path)
    with zipfile.ZipFile(archive, "a") as package:
        package.writestr("Yayu-1.0.4-windows-x64/" + name, "malicious fixture")
    with pytest.raises(engine.UpdateError):
        engine.prepare_update(archive, install, "1.0.4", engine._sha256(archive))
    assert not (install / engine.PENDING_MARKER).exists()


@pytest.mark.parametrize("name", ["DATA/config/api.local.yaml", "Data/config/api.yaml", ".YAYU-APP.LOCK", ".env", "LOGS/private.txt", "data/chat_history/default.json", "data/config/characters.example.yaml"])
def test_protected_manifest_paths_and_case_variants_rejected(tmp_path, install, name):
    archive = _archive(tmp_path, extra={name: "must never install"})
    with pytest.raises(engine.UpdateError):
        engine.prepare_update(archive, install, "1.0.4", engine._sha256(archive))


def test_zip_symlink_rejected(tmp_path, install):
    archive = _archive(tmp_path)
    with zipfile.ZipFile(archive, "a") as package:
        entry = zipfile.ZipInfo("Yayu-1.0.4-windows-x64/core/symlink.py")
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        package.writestr(entry, "../../user-profile")
    with pytest.raises(engine.UpdateError, match="链接"):
        engine.prepare_update(archive, install, "1.0.4", engine._sha256(archive))


def test_case_colliding_directory_prefixes_rejected(tmp_path, install):
    archive = _archive(tmp_path)
    with zipfile.ZipFile(archive, "a") as package:
        package.writestr("Yayu-1.0.4-windows-x64/CORE/another.py", "case collision")
    with pytest.raises(engine.UpdateError, match="大小写"):
        engine.prepare_update(archive, install, "1.0.4", engine._sha256(archive))


def test_expansion_limit_rejected(tmp_path, install, monkeypatch):
    archive = _archive(tmp_path)
    monkeypatch.setattr(engine, "MAX_UNPACKED_BYTES", 12)
    with pytest.raises(engine.UpdateError, match="大小"):
        engine._extract_verified(archive, tmp_path / "too-big-stage", "1.0.4")


@pytest.mark.parametrize("field,name", [("new_files", "DATA/config/api.local.yaml"), ("old_files", "logs/private.txt")])
def test_recovery_plan_repeats_complete_manifest_validation(tmp_path, install, field, name):
    prepared = _prepare(tmp_path, install)
    plan = json.loads(prepared.plan_path.read_text(encoding="utf-8"))
    plan[field][name] = {"path": name, "bytes": 0, "sha256": "0" * 64}
    prepared.plan_path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(engine.UpdateError):
        engine._load_plan(prepared.plan_path)


def test_program_file_removal_helper_cannot_delete_profile_aliases(install):
    for name in ("data/config/api.local.yaml", "DATA/config/api.local.yaml", "LOGS/user.log", ".YAYU-APP.LOCK"):
        with pytest.raises(engine.UpdateError):
            engine._remove_file(install, name)
    assert (install / "data/config/api.local.yaml").exists()


def test_failed_recovery_keeps_guard_and_journal_for_later_retry(tmp_path, install, monkeypatch):
    prepared = _prepare(tmp_path, install)
    plan = engine._load_plan(prepared.plan_path)
    engine._copy_backup(plan)
    engine._write_journal(plan, "installing")
    original_lock = engine.update_lock
    monkeypatch.setattr(engine, "update_lock", lambda root, timeout: original_lock(root, timeout=0))
    monkeypatch.setattr(engine, "_notify", lambda *args, **kwargs: None)
    from core.updates.locking import FileLock
    with FileLock(install / engine.APP_LOCK, exclusive=False):
        assert engine.run_worker(prepared.plan_path, recover=True) == 2
    assert (install / engine.PENDING_MARKER).exists()
    assert json.loads((prepared.plan_path.parent / "journal.json").read_text(encoding="utf-8"))["state"] == "recovery-required"


def test_unmanaged_runtime_files_refuse_without_deleting_anything(tmp_path, install):
    _write(install, "runtime/Lib/site-packages/custom-user-package.py", "keep")
    before = _snapshot(install)
    with pytest.raises(engine.UpdateError, match="清单以外"):
        _prepare(tmp_path, install)
    assert _snapshot(install) == before


def test_new_managed_path_cannot_overwrite_unmanaged_user_file(tmp_path, install):
    _write(install, "core/new-feature.py", "user work")
    with pytest.raises(engine.UpdateError, match="自行放置"):
        _prepare(tmp_path, install, **{"core/new-feature.py": "new published module"})
    assert (install / "core/new-feature.py").read_text() == "user work"


def test_cancel_unlaunched_preparation_removes_only_own_stage_and_marker(tmp_path, install):
    before = _snapshot(install)
    prepared = _prepare(tmp_path, install)
    engine.discard_prepared(prepared)
    assert not prepared.plan_path.parent.exists()
    assert _snapshot(install) == before


def test_discard_refuses_any_task_with_backup(tmp_path, install):
    prepared = _prepare(tmp_path, install)
    prepared.backup_dir.mkdir()
    with pytest.raises(engine.UpdateError, match="已启动"):
        engine.discard_prepared(prepared)
    assert prepared.backup_dir.is_dir()


def test_concurrent_prepare_refused(tmp_path, install):
    _prepare(tmp_path, install)
    with pytest.raises(engine.UpdateError, match="已有更新"):
        archive = _archive(tmp_path, version="1.0.5")
        engine.prepare_update(archive, install, "1.0.5", engine._sha256(archive))


def test_stage_tampering_after_prepare_fails_before_backup_or_program_changes(tmp_path, install, monkeypatch):
    before = _snapshot(install)
    prepared = _prepare(tmp_path, install)
    _write(prepared.plan_path.parent / "stage", "core/feature.py", "tampered")
    monkeypatch.setattr(engine, "_notify", lambda *args, **kwargs: None)
    assert engine.run_worker(prepared.plan_path) == 1
    assert not prepared.backup_dir.exists()
    assert {k: v for k, v in _snapshot(install).items() if not k.startswith(".yayu-")} == before


def test_health_marker_requires_same_token_and_installation(tmp_path, install, monkeypatch):
    prepared = _prepare(tmp_path, install)
    monkeypatch.delenv("YAYU_UPDATE_TOKEN", raising=False)
    assert not engine.mark_startup_healthy(install)
    monkeypatch.setenv("YAYU_UPDATE_TOKEN", "wrong-token")
    assert not engine.mark_startup_healthy(install)
    plan = engine._load_plan(prepared.plan_path)
    monkeypatch.setenv("YAYU_UPDATE_TOKEN", plan["token"])
    assert not engine.mark_startup_healthy(install)  # Still the previous version.
    _write(install, "VERSION", plan["version"])
    assert engine.mark_startup_healthy(install)
    assert json.loads((prepared.plan_path.parent / "healthy.json").read_text())["token"] == plan["token"]


def test_health_acceptance_does_not_traverse_private_backup_tree(tmp_path, install, monkeypatch):
    prepared = _prepare(tmp_path, install)
    plan = engine._load_plan(prepared.plan_path)
    _write(install, "VERSION", plan["version"])
    monkeypatch.setenv("YAYU_UPDATE_TOKEN", plan["token"])
    checks = []
    original_check = engine._assert_no_links

    def check(path, *, recursive=False):
        checks.append((path, recursive))
        return original_check(path, recursive=recursive)

    monkeypatch.setattr(engine, "_assert_no_links", check)
    assert engine.mark_startup_healthy(install)
    assert checks and not any(recursive for _, recursive in checks)


def test_plan_paths_cannot_escape_work_directory(tmp_path, install):
    prepared = _prepare(tmp_path, install)
    plan = json.loads(prepared.plan_path.read_text(encoding="utf-8"))
    plan["backup_dir"] = str(tmp_path / "outside")
    prepared.plan_path.write_text(json.dumps(plan))
    with pytest.raises(engine.UpdateError, match="边界"):
        engine._load_plan(prepared.plan_path)
