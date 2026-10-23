"""Cross-process lifetime locks for a portable installation (standard library only)."""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import time

APP_LOCK = ".yayu-app.lock"
PENDING_MARKER = ".yayu-update-pending.json"


def _fs(path: Path) -> Path:
    path = Path(path).absolute()
    value = str(path)
    if os.name == "nt" and not value.startswith("\\\\?\\"):
        value = "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value
        return Path(value)
    return path


class UpdateInProgressError(RuntimeError):
    pass


class FileLock:
    """Windows shared read handles / POSIX flock; never deletes the lock inode."""

    def __init__(self, path: Path, *, exclusive: bool, timeout: float = 0):
        self.path = _fs(path)
        self.exclusive = exclusive
        self.timeout = timeout
        self._handle = None

    def acquire(self):
        if self._handle is not None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Materialize once with sharing enabled before opening read-only shared locks.
        if not self.path.exists():
            with self.path.open("ab"):
                pass
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                if os.name == "nt":
                    import ctypes
                    from ctypes import wintypes
                    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                    create = kernel.CreateFileW
                    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                       wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
                    create.restype = wintypes.HANDLE
                    handle = create(str(self.path), 0x80000000 | (0x40000000 if self.exclusive else 0),
                                    0 if self.exclusive else 1, None, 3, 0x80, None)
                    if handle == wintypes.HANDLE(-1).value:
                        error = ctypes.get_last_error()
                        if error not in (32, 33):
                            raise ctypes.WinError(error)
                        raise BlockingIOError(error, "Installation is in use")
                    self._handle = handle
                else:
                    import fcntl
                    handle = self.path.open("rb")
                    try:
                        fcntl.flock(handle, (fcntl.LOCK_EX if self.exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
                    except BaseException:
                        handle.close()
                        raise
                    self._handle = handle
                return self
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("芽语仍在使用此目录，请关闭主界面和设置窗口后重试。") from None
                time.sleep(min(.1, max(0, deadline - time.monotonic())))

    def close(self):
        handle, self._handle = self._handle, None
        if handle is not None:
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes
                close = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
                close.argtypes = [wintypes.HANDLE]
                close(handle)
            else:
                import fcntl
                with contextlib.suppress(OSError):
                    fcntl.flock(handle, fcntl.LOCK_UN)
                handle.close()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *args):
        self.close()


class ApplicationLock(FileLock):
    def __init__(self, root: Path, *, timeout: float = 5):
        self.root = Path(root)
        super().__init__(self.root / APP_LOCK, exclusive=False, timeout=timeout)

    def acquire(self):
        super().acquire()
        marker = _fs(self.root / PENDING_MARKER)
        if marker.exists():
            try:
                pending = json.loads(marker.read_text(encoding="utf-8"))
                authorized = bool(pending.get("token")) and pending["token"] == os.environ.get("YAYU_UPDATE_TOKEN")
            except (OSError, ValueError):
                authorized = False
            if not authorized:
                self.close()
                raise UpdateInProgressError("芽语正在更新或等待恢复，请勿重复启动。更新标记：" + str(marker))
        return self


def application_lock(root: Path, *, timeout: float = 5) -> ApplicationLock:
    """Use as a context manager, or call .acquire() and retain until final exit."""
    return ApplicationLock(root, timeout=timeout)


def update_lock(root: Path, *, timeout: float = 120) -> FileLock:
    return FileLock(Path(root) / APP_LOCK, exclusive=True, timeout=timeout)
