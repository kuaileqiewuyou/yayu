"""Start the portable Windows package using only its own writable data directory.

The launcher invokes ``runtime/python.exe -E -u portable_bootstrap.py``.  Keep
project imports below the environment setup: several modules resolve local
configuration, logs and security permissions as soon as they are imported.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys

_DLL_DIRECTORY_HANDLES: dict[Path, object] = {}


def configure_native_libraries(root: Path) -> None:
    """Keep portable Qt and codec DLLs discoverable for native plugin loads."""
    if sys.platform != "win32":
        return
    dependencies = root / "runtime" / "Lib" / "site-packages"
    for name in ("PySide6", "shiboken6"):
        directory = dependencies / name
        if directory.is_dir() and directory not in _DLL_DIRECTORY_HANDLES:
            # Windows removes a DLL directory when this handle is collected.
            # Hold it for the process lifetime, including lazy audio playback.
            _DLL_DIRECTORY_HANDLES[directory] = os.add_dll_directory(str(directory))


def main(argv: list[str] | None = None) -> int:
    """Initialize missing defaults and open chat, or settings with ``--settings``.

    Existing settings and API overlays belong to the user and are left intact.
    Other arguments are passed through to Qt after the bootstrap-only flag has
    been removed.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    settings = "--settings" in arguments
    qt_arguments = [argument for argument in arguments if argument != "--settings"]

    root = Path(__file__).resolve().parent
    os.chdir(root)
    appdata = root / "data" / "appdata"
    appdata.mkdir(parents=True, exist_ok=True)
    os.environ["LOCALAPPDATA"] = str(appdata)
    os.environ["YAYU_PORTABLE_ROOT"] = str(root)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    # The portable runtime is launched with -E, so use the Python flag as well.
    sys.dont_write_bytecode = True

    entry_name = "webui_qt" if settings else "main"
    sys.argv = [str(root / f"{entry_name}.py"), *qt_arguments]

    # The launcher also holds this lock: both its EXE and the child runtime
    # must have exited before the detached updater can replace either one.
    from core.updates.locking import application_lock
    with application_lock(root):
        configure_native_libraries(root)
        initializer = importlib.import_module("scripts.init_config")
        initializer.initialize(root / "data" / "config", portable_resources=True)
        entry = importlib.import_module(entry_name)
        result = entry.main()
        return 0 if result is None else int(result)


if __name__ == "__main__":
    raise SystemExit(main())
