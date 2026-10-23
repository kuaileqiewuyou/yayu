"""Verified, recoverable portable upgrades. The copied worker needs only stdlib.

Only distribution-manifest files are replaced. Existing data and unrelated user
files are never overwritten; a closed-profile backup is made before mutations.
"""
from __future__ import annotations

import argparse
import contextlib
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid
import zipfile

try:
    from .locking import APP_LOCK, PENDING_MARKER, FileLock, update_lock
except ImportError:  # Independent copy outside the installation being replaced.
    from locking import APP_LOCK, PENDING_MARKER, FileLock, update_lock

MANIFEST = "PACKAGE_MANIFEST.json"
BUILD_INFO = "BUILD_INFO.json"
MAX_FILES = 60000
MAX_UNPACKED_BYTES = 4 * 1024**3
MAX_SINGLE_FILE_BYTES = 768 * 1024**2
MAX_METADATA_BYTES = 16 * 1024**2
REQUIRED = {"VERSION", BUILD_INFO, "portable_bootstrap.py", "Yayu.exe", "Yayu Settings.exe", "runtime/python.exe"}
PROGRAM_ROOTS = {"asr", "config", "core", "i18n", "llm", "plugins", "sdk", "t2i", "tts", "ui", "scripts", "runtime", "docs", "licenses"}
PROGRAM_FILES = {"main.py", "webui_qt.py", "portable_bootstrap.py", "VERSION", "README.md", "THIRD_PARTY_NOTICES.md",
                 "THIRD_PARTY_NOTICES.txt", "requirements.txt", "Yayu.exe", "Yayu Settings.exe", BUILD_INFO,
                 "QT_RUNTIME_MANIFEST.json", "开始使用.txt"}
_HEX = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[0-9a-f]{32}$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$")
_RESERVED = re.compile(r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$", re.I)


class UpdateError(RuntimeError):
    """User-actionable failure; the old installation/profile remains recoverable."""


@dataclass(frozen=True)
class PreparedUpdate:
    plan_path: Path
    backup_dir: Path


def _fs(path: Path) -> Path:
    """Win32 extended paths are essential for bundled upstream license trees."""
    path = Path(path).absolute()
    value = str(path)
    if os.name == "nt" and not value.startswith("\\\\?\\"):
        value = "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value
        return Path(value)
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with _fs(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_relative(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 500 or "\\" in value:
        raise UpdateError("更新包包含无效路径。")
    parts = value.split("/")
    if len(parts) > 40 or any(not part or part in {".", ".."} or part[-1:] in {".", " "}
                              or any(ord(c) < 32 or c in ':<>"|?*' for c in part)
                              or _RESERVED.fullmatch(part) for part in parts):
        raise UpdateError("更新包包含不安全的 Windows 路径：" + value)
    return PurePosixPath(value).as_posix()


def _assert_no_links(path: Path, *, recursive: bool = False) -> None:
    """Check existing ancestors before resolve(), including Windows junctions."""
    path = path.absolute()
    for part in [*reversed(path.parents), path]:
        try:
            info = _fs(part).lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise UpdateError("更新目录包含符号链接或重解析点，请先移至普通目录：" + str(part))
    if recursive and _fs(path).exists():
        for current, folders, files in os.walk(_fs(path), followlinks=False):
            for name in folders + files:
                _assert_no_links(Path(current) / name)


def _atomic_json(path: Path, value: object) -> None:
    path = _fs(path)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _read_json(path: Path, limit: int = MAX_METADATA_BYTES):
    path = _fs(path)
    if path.stat().st_size > limit:
        raise UpdateError("更新元数据过大：" + path.name)
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest(root: Path) -> dict[str, dict]:
    return _validate_manifest_items(_read_json(root / MANIFEST))


def _validate_manifest_items(raw: object) -> dict[str, dict]:
    if not isinstance(raw, list) or not raw or len(raw) > MAX_FILES:
        raise UpdateError("更新清单格式无效。")
    result, insensitive, total = {}, set(), 0
    for item in raw:
        if not isinstance(item, dict):
            raise UpdateError("更新清单条目无效。")
        name = _safe_relative(item.get("path"))
        if name.casefold() in insensitive or name == MANIFEST:
            raise UpdateError("更新清单存在重复路径。")
        if type(item.get("bytes")) is not int or not 0 <= item["bytes"] <= MAX_SINGLE_FILE_BYTES:
            raise UpdateError("更新清单的文件大小无效。")
        total += item["bytes"]
        if total > MAX_UNPACKED_BYTES:
            raise UpdateError("更新清单总大小超过安全限制。")
        if not isinstance(item.get("sha256"), str) or not _HEX.fullmatch(item["sha256"]):
            raise UpdateError("更新清单的 SHA256 无效。")
        if name.startswith("data/") and not _public_data_path(name):
            raise UpdateError("更新包包含非公开的用户数据路径：" + name)
        if not name.startswith("data/") and name not in PROGRAM_FILES and name.split("/", 1)[0] not in PROGRAM_ROOTS:
            raise UpdateError("更新包包含受保护路径：" + name)
        insensitive.add(name.casefold())
        result[name] = item
    if not REQUIRED <= result.keys():
        raise UpdateError("更新包缺少必要的程序或运行时文件。")
    return result


def _public_data_path(name: str) -> bool:
    if name == "data/config/api.yaml" or name == "data/character_templates/default.txt":
        return True
    if name.startswith("data/config/") and name.count("/") == 2 and name.endswith(".example.yaml") and not name.endswith("characters.example.yaml"):
        return True
    return name in {"data/characters/xiaoya/" + tail for tail in (
        "README.md", "character.yaml", "persona.md", "standing-neutral.png", "standing-wink.png", "standing-listening.png")}


def is_portable_install(root: Path) -> bool:
    root = _fs(root)
    try:
        _assert_no_links(root)
        if (root / ".git").exists() or (root / "venv").exists():
            return False
        if not all((root / name).is_file() for name in REQUIRED | {MANIFEST}):
            return False
        info = _read_json(root / BUILD_INFO)
        version = (root / "VERSION").read_text(encoding="utf-8").strip()
        return isinstance(info, dict) and bool(_VERSION.fullmatch(version)) and info.get("version") == version and bool(_manifest(root))
    except (OSError, ValueError, TypeError, UpdateError):
        return False


def _extract_verified(archive: Path, destination: Path, version: str) -> dict:
    destination = _fs(destination)
    with zipfile.ZipFile(_fs(archive)) as package:
        entries = package.infolist()
        if not entries or len(entries) > MAX_FILES:
            raise UpdateError("更新包文件数量异常。")
        total, names, paths, top_names = 0, set(), [], set()
        for entry in entries:
            name = entry.filename.rstrip("/") if entry.is_dir() else entry.filename
            name = _safe_relative(name)
            mode = entry.external_attr >> 16
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR) or entry.external_attr & 0x400:
                raise UpdateError("更新包包含链接或特殊文件。")
            if entry.flag_bits & 1 or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise UpdateError("更新包压缩格式不受支持。")
            key = name.casefold()
            if key in names:
                raise UpdateError("更新包包含重复或大小写冲突的文件。")
            names.add(key)
            total += entry.file_size
            if entry.file_size > MAX_SINGLE_FILE_BYTES or total > MAX_UNPACKED_BYTES:
                raise UpdateError("更新包解压大小超过安全限制。")
            if entry.file_size > max(1024**2, entry.compress_size * 1000):
                raise UpdateError("更新包压缩比例异常。")
            top_names.add(name.split("/", 1)[0])
            paths.append((entry, name))
        if top_names != {f"Yayu-{version}-windows-x64"}:
            raise UpdateError("更新包目录名称与目标版本不一致。")
        # Parent spelling collisions are dangerous even without explicit directory entries.
        spelling = {}
        for entry, name in paths:
            components = name.split("/")
            for index in range(1, len(components) + 1):
                prefix = "/".join(components[:index])
                old = spelling.setdefault(prefix.casefold(), prefix)
                if old != prefix:
                    raise UpdateError("更新包目录存在大小写冲突。")
        for entry, name in paths:
            relative = name.split("/", 1)
            if len(relative) == 1:
                continue
            target = destination / relative[1]
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(entry) as source, target.open("xb") as output:
                copied = 0
                while chunk := source.read(1024 * 1024):
                    copied += len(chunk)
                    if copied > entry.file_size:
                        raise UpdateError("更新包文件大小与声明不符。")
                    output.write(chunk)
            if copied != entry.file_size:
                raise UpdateError("更新包文件不完整。")
    manifest = _manifest(destination)
    present = {p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()}
    if present != set(manifest) | {MANIFEST}:
        raise UpdateError("更新包文件与发行清单不一致。")
    for name, metadata in manifest.items():
        path = destination / name
        if path.stat().st_size != metadata["bytes"] or _sha256(path) != metadata["sha256"]:
            raise UpdateError("更新包内部校验失败：" + name)
    if (destination / "VERSION").read_text(encoding="utf-8").strip() != version:
        raise UpdateError("更新包 VERSION 不匹配。")
    if _read_json(destination / BUILD_INFO).get("version") != version:
        raise UpdateError("更新包构建信息版本不匹配。")
    return manifest


def _check_installation_files(root: Path, old: dict, new: dict):
    root = _fs(root)
    _assert_no_links(root, recursive=True)
    for name in new:
        if name.startswith("data/"):
            continue
        destination = root / name
        if destination.exists() and name not in old:
            raise UpdateError("新版文件与您自行放置的文件冲突，未做修改：" + str(destination))
        if destination.exists() and not destination.is_file():
            raise UpdateError("程序文件被同名目录占用：" + str(destination))
    runtime = root / "runtime"
    for path in runtime.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        generated = "__pycache__" in path.relative_to(runtime).parts and path.suffix == ".pyc"
        if relative not in old and not generated:
            raise UpdateError("runtime 中有发行清单以外的文件，请先移出并保留：" + str(path))


def _copy_worker(root: Path, work: Path):
    root, work = _fs(root), _fs(work)
    shutil.copy2(_fs(Path(__file__)), work / "installer.py")
    shutil.copy2(_fs(Path(__file__).with_name("locking.py")), work / "locking.py")
    runtime = work / "worker-runtime"
    runtime.mkdir()
    for path in (root / "runtime").iterdir():
        if path.is_file():
            shutil.copy2(path, runtime / path.name)
    pth_files = list(runtime.glob("python*._pth"))
    for path in pth_files:
        path.write_text("\n".join(p.name for p in sorted(runtime.glob("python*.zip"))) + "\n.\n..\n", encoding="utf-8")


def prepare_update(archive: Path, app_root: Path, expected_version: str, expected_sha256: str, progress=None) -> PreparedUpdate:
    """Validate and stage without changing program/data; set the launch guard last."""
    root, archive = Path(app_root).absolute(), Path(archive).absolute()
    if not is_portable_install(root):
        raise UpdateError("一键更新仅支持完整的 Windows 便携版；源码目录请通过 Git 更新。")
    if not _VERSION.fullmatch(expected_version) or not _HEX.fullmatch(expected_sha256.lower()):
        raise UpdateError("目标版本或 SHA256 格式无效。")
    _assert_no_links(archive)
    if not _fs(archive).is_file() or _sha256(archive) != expected_sha256.lower():
        raise UpdateError("下载文件 SHA256 校验失败，未修改现有程序。")
    work_parent = root.parent / ".yayu-updates"
    _assert_no_links(work_parent)
    _fs(work_parent).mkdir(exist_ok=True)
    # Only preparation is serialized here; the independent worker owns worker.lock.
    with FileLock(work_parent / (hashlib.sha256(str(root).casefold().encode()).hexdigest() + ".lock"), exclusive=True):
        if _fs(root / PENDING_MARKER).exists():
            raise UpdateError("已有更新正在进行或等待恢复，请先完成上一次更新。")
        token = uuid.uuid4().hex
        work = work_parent / token
        _fs(work).mkdir()
        stage, backup = work / "stage", work / "backup"
        _fs(stage).mkdir()
        if progress:
            progress("正在校验并准备更新包…")
        try:
            new = _extract_verified(archive, stage, expected_version)
            old = _manifest(root)
            _check_installation_files(root, old, new)
            # Backup and replacement coexist until acceptance; reserve adequate space.
            needed = sum(p.stat().st_size for p in _fs(root).rglob("*") if p.is_file())
            if shutil.disk_usage(_fs(work)).free < needed * 2 + 64 * 1024**2:
                raise UpdateError("磁盘可用空间不足以保留更新备份。")
            _copy_worker(root, work)
            plan = {"schema_version": 1, "token": token, "app_root": str(root), "work_dir": str(work),
                    "stage_dir": str(stage), "backup_dir": str(backup), "version": expected_version,
                    "old_files": old, "new_files": new, "restart_exe": "Yayu.exe",
                    "wait_timeout": 120, "health_timeout": 120,
                    "recovery_python": str(work / "worker-runtime" / "python.exe"),
                    "recovery_script": str(work / "installer.py")}
            _atomic_json(work / "plan.json", plan)
            _write_pending(plan, "prepared")
            return PreparedUpdate(work / "plan.json", backup)
        except BaseException:
            # This directory was created by this call and has no profile backup.
            _safe_remove_work(work, root, token)
            raise


def _safe_remove_work(work: Path, root: Path, token: str):
    expected = root.parent / ".yayu-updates" / token
    if not _TOKEN.fullmatch(token) or work.absolute() != expected.absolute():
        raise UpdateError("拒绝清理更新目录边界以外的路径。")
    _assert_no_links(work, recursive=True)
    if _fs(work / "backup").exists() or _fs(work / "ready.json").exists() or _fs(work / "journal.json").exists():
        raise UpdateError("已启动的更新或已有备份不能作为暂存目录删除。")
    if _fs(work).exists():
        shutil.rmtree(_fs(work))


def discard_prepared(prepared: PreparedUpdate) -> None:
    """Cancel only this unlaunched preparation. Never deletes a backup or journal."""
    plan = _load_plan(prepared.plan_path)
    root, work = Path(plan["app_root"]), Path(plan["work_dir"])
    marker = _fs(root / PENDING_MARKER)
    pending = _read_json(marker) if marker.exists() else None
    if pending is not None and (pending.get("token") != plan["token"] or pending.get("state") != "prepared"):
        raise UpdateError("此更新已开始或已被其他事务接管，不能取消。")
    with FileLock(work / "worker.lock", exclusive=True):
        # Worker writes ready before attempting any changes, and holds this lock.
        if _fs(work / "ready.json").exists() or _fs(work / "journal.json").exists() or _fs(work / "backup").exists():
            raise UpdateError("更新已启动，不能删除恢复文件。")
        if pending is not None:
            _clear_pending(plan)
    _safe_remove_work(work, root, plan["token"])


def _load_plan(path: Path, *, verify_tree: bool = True) -> dict:
    _assert_no_links(path)
    plan = _read_json(path)
    if not isinstance(plan, dict) or plan.get("schema_version") != 1 or not _TOKEN.fullmatch(plan.get("token", "")):
        raise UpdateError("更新恢复计划无效。")
    root = Path(plan["app_root"]).absolute()
    work = root.parent / ".yayu-updates" / plan["token"]
    for field, expected in {"work_dir": work, "stage_dir": work / "stage", "backup_dir": work / "backup",
                            "recovery_python": work / "worker-runtime" / "python.exe", "recovery_script": work / "installer.py"}.items():
        if Path(plan.get(field, "")).absolute() != expected:
            raise UpdateError("更新计划包含目录边界以外的路径。")
    if Path(path).absolute() != work / "plan.json":
        raise UpdateError("更新计划不在正确的恢复目录内。")
    _assert_no_links(root)
    _assert_no_links(work, recursive=verify_tree)
    for field in ("old_files", "new_files"):
        if not isinstance(plan.get(field), dict) or len(plan[field]) > MAX_FILES:
            raise UpdateError("更新计划文件清单无效。")
        validated = _validate_manifest_items(list(plan[field].values()))
        if validated != plan[field]:
            raise UpdateError("更新计划路径与文件元数据不一致。")
    if plan.get("restart_exe") not in {"Yayu.exe", "Yayu Settings.exe"}:
        raise UpdateError("更新计划的重启程序无效。")
    if not isinstance(plan.get("version"), str) or not _VERSION.fullmatch(plan["version"]):
        raise UpdateError("更新计划版本无效。")
    for field in ("wait_timeout", "health_timeout"):
        if type(plan.get(field)) not in (int, float) or not 0 < plan[field] <= 600:
            raise UpdateError("更新计划等待时间无效。")
    return plan


def _write_pending(plan: dict, state: str):
    work = Path(plan["work_dir"])
    target = _fs(Path(plan["app_root"]) / PENDING_MARKER)
    if target.exists():
        if _read_json(target).get("token") != plan["token"]:
            raise UpdateError("另一个更新事务已接管此目录，拒绝覆盖其恢复标记。")
    elif state != "prepared":
        raise UpdateError("更新准备已被取消或结束，拒绝重新启动旧更新。")
    marker = {key: plan[key] for key in ("token", "app_root", "backup_dir", "recovery_python", "recovery_script", "version")}
    marker.update(plan_path=str(work / "plan.json"), state=state, worker_pid=os.getpid())
    _atomic_json(target, marker)


def _clear_pending(plan: dict):
    marker = _fs(Path(plan["app_root"]) / PENDING_MARKER)
    if marker.exists() and _read_json(marker).get("token") == plan["token"]:
        marker.unlink()


def _write_journal(plan: dict, state: str, **extra):
    _atomic_json(Path(plan["work_dir"]) / "journal.json", {"state": state, "time": time.time(), **extra})
    _write_pending(plan, state)


def launch_update(prepared: PreparedUpdate) -> subprocess.Popen:
    return _launch_worker(prepared.plan_path, recover=False)


def _launch_worker(plan_path: Path, *, recover: bool) -> subprocess.Popen:
    plan = _load_plan(plan_path)
    work = _fs(Path(plan["work_dir"]))
    ready = work / "ready.json"
    if ready.exists():
        ready.unlink()
    arguments = [plan["recovery_python"], "-E", "-u", plan["recovery_script"], "--recover" if recover else "--worker", str(plan_path)]
    environment = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        environment.pop(key, None)
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    log = (work / "worker.log").open("ab")
    try:
        process = subprocess.Popen(arguments, cwd=work, env=environment, creationflags=flags,
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
    finally:
        log.close()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if ready.exists() and _read_json(ready).get("pid") == process.pid:
            if not recover:
                _atomic_json(work / "proceed.json", {"pid": process.pid, "token": plan["token"]})
            return process
        if process.poll() is not None:
            _atomic_json(work / "cancel.json", {"pid": process.pid, "token": plan["token"]})
            raise UpdateError("独立更新程序启动失败，现有程序尚未关闭。详细记录：" + str(work / "worker.log"))
        time.sleep(.05)
    # Do not close the application unless the independent worker has acknowledged readiness.
    _atomic_json(work / "cancel.json", {"pid": process.pid, "token": plan["token"]})
    raise UpdateError("独立更新程序未能就绪，未要求应用退出。请查看：" + str(work / "worker.log"))


def recover_pending_update(root: Path) -> subprocess.Popen | None:
    """Resume rollback after interruption; caller must then exit and release app locks."""
    marker = _fs(Path(root) / PENDING_MARKER)
    if not marker.exists():
        return None
    pending = _read_json(marker)
    plan = _load_plan(Path(pending["plan_path"]))
    if Path(plan["app_root"]).absolute() != Path(root).absolute() or plan["token"] != pending.get("token"):
        raise UpdateError("更新恢复标记与本目录不匹配。")
    return _launch_worker(Path(pending["plan_path"]), recover=True)


def mark_startup_healthy(root: Path) -> bool:
    """Call after the real main/settings window has been shown successfully."""
    token = os.environ.get("YAYU_UPDATE_TOKEN", "")
    marker = _fs(Path(root) / PENDING_MARKER)
    if not token or not marker.is_file():
        return False
    try:
        pending = _read_json(marker)
        if pending.get("token") != token:
            return False
        # Acceptance only writes a fixed token marker. Full stage/profile tree
        # validation belongs to the independent worker, not the UI startup path.
        plan = _load_plan(Path(pending["plan_path"]), verify_tree=False)
        if Path(plan["app_root"]).absolute() != Path(root).absolute():
            return False
        if _fs(Path(root) / "VERSION").read_text(encoding="utf-8").strip() != plan["version"]:
            return False
        _atomic_json(Path(plan["work_dir"]) / "healthy.json", {"token": token, "pid": os.getpid(), "time": time.time()})
        return True
    except (OSError, ValueError, UpdateError):
        return False


def _copy_backup(plan: dict):
    root, backup = _fs(Path(plan["app_root"])), _fs(Path(plan["backup_dir"]))
    backup.mkdir()
    _assert_no_links(root, recursive=True)
    if (root / "data").exists():
        shutil.copytree(root / "data", backup / "data")
    managed = backup / "managed"
    for name in [*plan["old_files"], MANIFEST]:
        if name.startswith("data/"):
            continue
        source = root / name
        if source.is_file():
            target = managed / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    _atomic_json(backup / "backup-complete.json", {"token": plan["token"], "time": time.time()})


def _remove_file(root: Path, relative: str):
    root = _fs(root)
    relative = _safe_relative(relative)
    if relative.split("/", 1)[0].casefold() in {"data", "logs"} or relative.casefold().startswith(".yayu-"):
        raise UpdateError("拒绝删除用户数据或更新锁：" + relative)
    target = root / relative
    _assert_no_links(target)
    if target.is_file():
        target.unlink()


def _apply_files(plan: dict):
    root, stage = _fs(Path(plan["app_root"])), _fs(Path(plan["stage_dir"]))
    old_runtime = root / "runtime"
    saved_runtime = _fs(Path(plan["work_dir"])) / "old-runtime"
    if old_runtime.exists():
        os.replace(old_runtime, saved_runtime)
    shutil.copytree(stage / "runtime", old_runtime)
    for name in plan["old_files"]:
        if name.split("/", 1)[0].casefold() == "data" or name.startswith("runtime/"):
            continue
        if name not in plan["new_files"]:
            _remove_file(root, name)
    added_data = []
    # Journal each new public-data file before it is created, for crash rollback.
    for name in [*plan["new_files"], MANIFEST]:
        if name.startswith("runtime/") or name == "data/config/api.yaml":
            continue
        target = root / name
        _assert_no_links(target)
        if name.split("/", 1)[0].casefold() == "data":
            if target.exists():
                continue
            if not name.startswith("data/") or not _public_data_path(name):
                raise UpdateError("拒绝写入用户数据：" + name)
            added_data.append(name)
            _atomic_json(Path(plan["work_dir"]) / "added-data.json", added_data)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".yayu-new-" + plan["token"])
        shutil.copy2(stage / name, temporary)
        os.replace(temporary, target)


def _safe_remove_runtime(plan: dict):
    root = _fs(Path(plan["app_root"]))
    runtime = root / "runtime"
    if runtime.parent != root or runtime.name != "runtime":
        raise UpdateError("拒绝删除目录边界之外的运行时。")
    _assert_no_links(runtime, recursive=True)
    if runtime.exists():
        shutil.rmtree(runtime)


def _rollback(plan: dict):
    root, backup, work = _fs(Path(plan["app_root"])), _fs(Path(plan["backup_dir"])), _fs(Path(plan["work_dir"]))
    if not (backup / "backup-complete.json").exists():
        # Program mutation starts strictly after the complete backup marker.
        return
    _safe_remove_runtime(plan)
    saved_runtime = work / "old-runtime"
    if saved_runtime.exists():
        os.replace(saved_runtime, root / "runtime")
    else:
        shutil.copytree(backup / "managed" / "runtime", root / "runtime")
    for name in plan["new_files"]:
        if name.split("/", 1)[0].casefold() != "data" and not name.startswith("runtime/") and name not in plan["old_files"]:
            _remove_file(root, name)
    for name in [*plan["old_files"], MANIFEST]:
        if name.split("/", 1)[0].casefold() == "data" or name.startswith("runtime/"):
            continue
        source = backup / "managed" / name
        if source.is_file():
            target = root / name
            _assert_no_links(source)
            _assert_no_links(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".yayu-restore-" + plan["token"])
            shutil.copy2(source, temporary)
            os.replace(temporary, target)
    # Never restore the data snapshot over a user's current profile. It is a
    # separate, explicit recovery copy; existing data wasn't replaced by us.
    added = work / "added-data.json"
    if added.exists():
        for name in _read_json(added):
            path = root / _safe_relative(name)
            metadata = plan["new_files"].get(name)
            if name.startswith("data/") and _public_data_path(name) and metadata and path.is_file() and _sha256(path) == metadata["sha256"]:
                _assert_no_links(path)
                path.unlink()


def _notify(message: str, *, error: bool = False):
    print(message, flush=True)
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "芽语 / Yayu 更新", 0x10 if error else 0x40)


def _restart(plan: dict):
    root = Path(plan["app_root"])
    environment = os.environ.copy()
    environment["YAYU_UPDATE_TOKEN"] = plan["token"]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.Popen([str(root / plan.get("restart_exe", "Yayu.exe"))], cwd=root, env=environment, creationflags=flags)


def _await_health(plan: dict, process) -> bool:
    deadline = time.monotonic() + float(plan.get("health_timeout", 120))
    health = _fs(Path(plan["work_dir"])) / "healthy.json"
    while time.monotonic() < deadline:
        if health.is_file() and _read_json(health).get("token") == plan["token"]:
            return True
        if process.poll() is not None:
            return False
        time.sleep(.1)
    return False


def _request_close_installation_windows(root: Path):
    """Request normal window close on timeout; never terminate user processes."""
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes
    kernel, user = ctypes.WinDLL("kernel32", use_last_error=True), ctypes.WinDLL("user32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    prefix = str(root.absolute()).rstrip("\\/").casefold() + "\\"

    @callback_type
    def callback(hwnd, _):
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel.OpenProcess(0x1000, False, pid.value)
        if handle:
            try:
                length, image = wintypes.DWORD(32768), ctypes.create_unicode_buffer(32768)
                if kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length)) and image.value.casefold().startswith(prefix):
                    user.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE follows normal save/exit paths.
            finally:
                kernel.CloseHandle(handle)
        return True

    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.EnumWindows(callback, 0)


def run_worker(plan_path: Path, *, recover: bool = False, require_launch_ack: bool = False) -> int:
    plan = _load_plan(Path(plan_path))
    root, work = Path(plan["app_root"]), _fs(Path(plan["work_dir"]))
    with FileLock(work / "worker.lock", exclusive=True):
        _write_pending(plan, "waiting")
        _atomic_json(work / "ready.json", {"pid": os.getpid(), "token": plan["token"]})
        if require_launch_ack and not recover:
            deadline = time.monotonic() + 25
            while True:
                if (work / "cancel.json").exists() or time.monotonic() >= deadline:
                    _clear_pending(plan)
                    _atomic_json(work / "journal.json", {"state": "cancelled-before-install", "time": time.time()})
                    return 1
                proceed = work / "proceed.json"
                if proceed.exists():
                    acknowledgement = _read_json(proceed)
                    if acknowledgement.get("pid") == os.getpid() and acknowledgement.get("token") == plan["token"]:
                        break
                time.sleep(.05)
        lock = update_lock(root, timeout=float(plan.get("wait_timeout", 120)))
        mutation = False
        try:
            lock.acquire()
            journal = work / "journal.json"
            previous = _read_json(journal).get("state") if journal.exists() else "prepared"
            if recover:
                if previous in {"backed-up", "installing", "installed", "waiting-health", "recovery-required"}:
                    _rollback(plan)
                    _write_journal(plan, "rolled-back")
                _clear_pending(plan)
                lock.close()
                _restart(plan)
                _notify("已恢复更新前的程序。角色、配置和聊天仍保留在原目录。\n备份：" + plan["backup_dir"])
                return 0
            _check_installation_files(root, plan["old_files"], plan["new_files"])
            # Recheck staged hashes immediately before touching the installation.
            for name, metadata in plan["new_files"].items():
                staged = _fs(Path(plan["stage_dir"])) / name
                if not staged.is_file() or _sha256(staged) != metadata["sha256"]:
                    raise UpdateError("更新暂存文件校验失败：" + name)
            _write_journal(plan, "backing-up")
            _copy_backup(plan)
            _write_journal(plan, "backed-up")
            mutation = True
            _write_journal(plan, "installing")
            _apply_files(plan)
            _write_journal(plan, "installed")
            lock.close()
            process = _restart(plan)
            _write_journal(plan, "waiting-health")
            if not _await_health(plan, process):
                # Never kill a live app or copy files over it. If it remains open,
                # leave a guarded recovery transaction for after it is closed.
                _request_close_installation_windows(root)
                lock = update_lock(root, timeout=15)
                try:
                    lock.acquire()
                except TimeoutError:
                    _write_journal(plan, "recovery-required")
                    _notify("新版未能确认启动成功，仍有窗口使用此目录。请关闭芽语全部窗口后重新启动以恢复旧版。\n未覆盖您的角色、配置或聊天。\n备份：" + plan["backup_dir"], error=True)
                    return 2
                raise UpdateError("新版启动未通过检查，已尝试恢复旧版。")
            _write_journal(plan, "complete")
            _clear_pending(plan)
            return 0
        except BaseException as error:
            if recover:
                _write_journal(plan, "recovery-required", error=str(error))
                lock.close()
                _notify("恢复暂未完成，请关闭芽语所有窗口后重试。\n备份与恢复文件已保留：" + plan["backup_dir"] + "\n原因：" + str(error), error=True)
                return 2
            if mutation:
                try:
                    if lock._handle is None:
                        lock = update_lock(root, timeout=5).acquire()
                    _rollback(plan)
                    _write_journal(plan, "rolled-back", error=str(error))
                    _clear_pending(plan)
                    lock.close()
                    try:
                        _restart(plan)
                    except OSError as restart_error:
                        print("旧版已恢复，请手动启动：" + str(restart_error), flush=True)
                except BaseException as rollback_error:
                    _write_journal(plan, "recovery-required", error=str(error), rollback_error=str(rollback_error))
                    lock.close()
                    _notify("更新中断，尚不能完成恢复。请关闭所有芽语窗口后重新启动。\n备份：" + plan["backup_dir"] + "\n原因：" + str(rollback_error), error=True)
                    return 2
            else:
                _write_journal(plan, "failed-before-install", error=str(error))
                _clear_pending(plan)
                lock.close()
            _notify("更新未完成：" + str(error) + "\n原角色、配置和聊天未被覆盖。\n备份位置：" + plan["backup_dir"], error=True)
            return 1
        finally:
            lock.close()


def _main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--worker", type=Path)
    mode.add_argument("--recover", type=Path)
    args = parser.parse_args()
    try:
        return run_worker(args.recover or args.worker, recover=args.recover is not None,
                          require_launch_ack=args.worker is not None)
    except BaseException as error:
        _notify("更新程序无法启动：" + str(error), error=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(_main())
