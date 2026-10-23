"""Keep an audited Windows Qt runtime, checking PE imports before deleting files.

This tool only operates inside a newly built portable package. It never searches
the host PATH or copies host DLLs. The dependency report is relative and can be
published with the package. Qt/PySide license and distribution metadata outside
the PySide6 directory are deliberately retained by the caller.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import struct


QT_MODULES = frozenset({"QtCore", "QtGui", "QtWidgets", "QtNetwork", "QtSvg", "QtMultimedia"})
# Only modules offering LGPLv3 are eligible. Required transitive modules still
# have to be discovered from the actual wheel's PE import tables.
QT_DLLS = frozenset({"qt6core.dll", "qt6gui.dll", "qt6widgets.dll", "qt6network.dll", "qt6svg.dll", "qt6multimedia.dll"})
VENDOR_DLLS = frozenset({"pyside6.abi3.dll", "shiboken6.abi3.dll", "python3.dll", "python313.dll",
    "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "vcruntime140.dll", "vcruntime140_1.dll",
    "avcodec-61.dll", "avformat-61.dll", "avutil-59.dll", "swresample-5.dll", "swscale-8.dll"})
PLUGINS = frozenset({
    "plugins/platforms/qwindows.dll",
    "plugins/styles/qmodernwindowsstyle.dll",
    "plugins/iconengines/qsvgicon.dll",
    "plugins/imageformats/qgif.dll", "plugins/imageformats/qico.dll",
    "plugins/imageformats/qjpeg.dll", "plugins/imageformats/qsvg.dll",
    "plugins/imageformats/qwebp.dll", "plugins/imageformats/qtiff.dll",
    "plugins/multimedia/ffmpegmediaplugin.dll",
    "plugins/multimedia/windowsmediaplugin.dll",
    "plugins/networkinformation/qnetworklistmanager.dll",
    "plugins/tls/qcertonlybackend.dll", "plugins/tls/qschannelbackend.dll",
})
# Windows API contracts and these OS DLLs are provided by supported Windows;
# they are never copied from System32. New imports require review, not PATH lookup.
SYSTEM_DLLS = frozenset(name.lower() for name in """
ADVAPI32.dll AVRT.dll bcrypt.dll CFGMGR32.dll COMCTL32.dll COMDLG32.dll
CRYPT32.dll d3d11.dll d3d12.dll d3d9.dll D3DCOMPILER_47.dll dcomp.dll
DNSAPI.dll dsound.dll DWMAPI.dll dxgi.dll dxva2.dll GDI32.dll GLU32.dll
IMM32.dll IPHLPAPI.DLL KERNEL32.dll Ksuser.dll MF.dll MFPlat.dll MFReadWrite.dll
mfuuid.dll MPR.dll MSASN1.dll MSVCRT.dll NETAPI32.dll NTDLL.dll OLE32.dll
OLEACC.dll OLEAUT32.dll OPENGL32.dll PowrProf.dll PROPSYS.dll PSAPI.DLL
RPCRT4.dll Secur32.dll SETUPAPI.dll SHCORE.dll SHELL32.dll SHLWAPI.dll
USER32.dll USERENV.dll USP10.dll UxTheme.dll VERSION.dll WINHTTP.dll
WININET.dll WINMM.dll WINTRUST.dll WLDAP32.dll WSOCK32.dll WS2_32.dll
WTSAPI32.dll WER.dll NORMALIZ.dll WINDOWSAPP.dll WINSPool.DRV
AUTHZ.dll DWRITE.dll UIAUTOMATIONCORE.dll NCRYPT.dll EVR.dll
""".split())


def _native_path(path: Path) -> Path:
    """Do not silently miss long wheel paths under Windows MAX_PATH."""
    if os.name != "nt" or str(path).startswith("\\\\?\\"):
        return path
    value = str(path)
    return Path("\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value)


def pe_imports(path: Path) -> set[str]:
    """Read standard and delay-load DLL imports of a PE32/PE32+ image."""
    data = path.read_bytes()

    def unpack(fmt: str, offset: int):
        try:
            return struct.unpack_from(fmt, data, offset)
        except struct.error as error:
            raise ValueError(f"Truncated PE: {path.name}") from error

    if data[:2] != b"MZ":
        raise ValueError(f"Not a PE image: {path.name}")
    pe = unpack("<I", 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError(f"Invalid PE signature: {path.name}")
    sections = unpack("<H", pe + 6)[0]
    optional_size = unpack("<H", pe + 20)[0]
    optional = pe + 24
    magic = unpack("<H", optional)[0]
    if magic == 0x20B:
        directories, imagebase = optional + 112, unpack("<Q", optional + 24)[0]
    elif magic == 0x10B:
        directories, imagebase = optional + 96, unpack("<I", optional + 28)[0]
    else:
        raise ValueError(f"Unsupported PE optional header: {path.name}")
    section_table = optional + optional_size
    ranges = []
    for index in range(sections):
        virtual_size, rva, raw_size, raw = unpack("<IIII", section_table + index * 40 + 8)
        ranges.append((rva, rva + max(virtual_size, raw_size), raw))

    def offset(rva: int) -> int:
        for start, end, raw in ranges:
            if start <= rva < end:
                result = raw + rva - start
                if result >= len(data):
                    break
                return result
        raise ValueError(f"Invalid PE RVA in {path.name}: {rva:x}")

    def string(rva: int) -> str:
        start = offset(rva)
        end = data.find(b"\0", start, start + 1024)
        if end < 0:
            raise ValueError(f"Invalid PE string: {path.name}")
        return data[start:end].decode("ascii").lower()

    imports = set()
    for table_index, record_size, name_index in ((1, 20, 3), (13, 32, 1)):
        rva, size = unpack("<II", directories + table_index * 8)
        if not rva:
            continue
        cursor = offset(rva)
        limit = cursor + size if size else len(data)
        while cursor + record_size <= min(limit, len(data)):
            fields = unpack("<" + "I" * (record_size // 4), cursor)
            if not any(fields):
                break
            name = fields[name_index]
            if table_index == 13 and not fields[0] & 1:
                name -= imagebase
            imports.add(string(name))
            cursor += record_size
        else:
            raise ValueError(f"Unterminated PE import table: {path.name}")
    return imports


def application_qt_imports(package: Path) -> set[str]:
    """Check runtime imports, excluding tests and build/snapshot tools."""
    found = set()
    candidates = [package / "main.py", package / "webui_qt.py"]
    for folder in ("core", "ui", "config", "tts", "llm", "sdk", "asr", "t2i", "plugins"):
        candidates.extend((package / folder).rglob("*.py"))
    for source in candidates:
        if not source.is_file():
            continue
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8-sig"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "PySide6":
                    found.update(alias.name for alias in node.names if alias.name.startswith("Qt"))
                elif node.module.startswith("PySide6."):
                    found.add(node.module.split(".")[1])
            elif isinstance(node, ast.Import):
                found.update(alias.name.split(".")[1] for alias in node.names if alias.name.startswith("PySide6.Qt"))
    if found - QT_MODULES:
        raise ValueError("Unaudited Qt application imports: " + repr(sorted(found - QT_MODULES)))
    return found


def _guard(package: Path) -> tuple[Path, Path]:
    package = _native_path(package.resolve(strict=True))
    runtime = package / "runtime"
    qt = runtime / "Lib/site-packages/PySide6"
    if not (package / "portable_bootstrap.py").is_file() or not (runtime / "python.exe").is_file():
        raise ValueError("Not a portable package build directory")
    if not qt.is_dir() or not qt.resolve().is_relative_to(package):
        raise ValueError("Qt directory is outside the portable package")
    if "venv" in qt.resolve().parts or ".venv" in qt.resolve().parts:
        raise ValueError("Refusing to modify a development virtual environment")
    for path in qt.rglob("*"):
        if path.is_symlink() or not path.resolve().is_relative_to(qt.resolve()):
            raise ValueError("Linked paths are not accepted in a Qt package")
    return package, qt


def runtime_plan(package: Path) -> dict:
    """Compute and validate the retained files without changing the package."""
    package, qt = _guard(package)
    found = application_qt_imports(package)
    version_file = qt / "_config.py"
    if not version_file.is_file() or "6.8.3" not in version_file.read_text(encoding="utf-8"):
        raise ValueError("Only the audited PySide6/Qt 6.8.3 wheel is supported")
    files = {path.relative_to(qt).as_posix(): path for path in qt.rglob("*") if path.is_file()}
    keep = set(PLUGINS)
    keep.update(module + ".pyd" for module in QT_MODULES)
    missing = keep - files.keys()
    if missing:
        raise ValueError("Incomplete Qt wheel: " + repr(sorted(missing)))
    # Keep package initialization/signature support and all shipped license texts.
    keep.update(name for name in files if name in {"__init__.py", "_config.py", "_git_pyside_version.py", "py.typed"}
                or name.startswith("support/") or "license" in name.lower() or "copying" in name.lower())
    # Only translations of retained Qt modules; no QML or WebEngine resources.
    keep.update(name for name in files if name.startswith("translations/") and
                Path(name).name.startswith(("qtbase_", "qtmultimedia_")) and name.endswith(".qm"))
    # Preserve matching module metadata/types without shipping unused module code.
    keep.update(name for name in files if any(name == module + ".pyi" or
                name == "metatypes/qt6" + module[2:].lower() + "_metatypes.json" for module in QT_MODULES))
    local_dlls = {}
    for path in (qt, qt.parent / "shiboken6", package / "runtime"):
        for candidate in path.glob("*"):
            if candidate.suffix.lower() in {".dll", ".pyd"}:
                local_dlls.setdefault(candidate.name.lower(), candidate)
    pending = [files[name] for name in keep if files[name].suffix.lower() in {".dll", ".pyd"}]
    pending.extend((qt.parent / "shiboken6").glob("*.pyd"))
    dependencies = {}
    while pending:
        binary = pending.pop()
        relative = binary.relative_to(package).as_posix()
        if relative in dependencies:
            continue
        imported = pe_imports(binary)
        dependencies[relative] = sorted(imported)
        for name in imported:
            if name.startswith("qt6") and name not in QT_DLLS:
                raise ValueError(f"Unaudited Qt dependency: {binary.name} -> {name}")
            target = local_dlls.get(name)
            if target:
                if name not in QT_DLLS | VENDOR_DLLS:
                    raise ValueError(f"Unaudited packaged dependency: {binary.name} -> {name}")
                if target.is_relative_to(qt):
                    keep.add(target.relative_to(qt).as_posix())
                pending.append(target)
            elif name in SYSTEM_DLLS or name.startswith(("api-ms-win-", "ext-ms-win-")):
                continue
            else:
                raise ValueError(f"Unresolved or unaudited DLL: {binary.name} -> {name}")
    retained = sorted(keep)
    return {"qt_version": "6.8.3", "application_modules": sorted(found),
            "bindings": sorted(QT_MODULES), "kept": retained,
            "qt_libraries": sorted(name for name in keep if name.lower() in QT_DLLS),
            "third_party_libraries": sorted(name for name in keep if name.lower() in VENDOR_DLLS),
            "plugins": sorted(PLUGINS),
            "removed": sorted(files.keys() - keep), "dependencies": dependencies,
            "bytes_before": sum(path.stat().st_size for path in files.values()),
            "bytes_after": sum(files[name].stat().st_size for name in keep)}


def prune_qt_runtime(dependencies: Path, package: Path) -> dict:
    """Apply the validated allowlist inside this portable package only."""
    package, qt = _guard(package)
    if _native_path(dependencies.resolve(strict=True)) != qt.parent:
        raise ValueError("Dependencies directory must be this package's runtime site-packages")
    report = runtime_plan(package)
    # Resolve every target before the first mutation. No recursive shell delete.
    targets = [qt / name for name in report["removed"]]
    if any(not path.resolve().is_relative_to(qt) for path in targets):
        raise ValueError("A deletion target escapes the Qt directory")
    for path in targets:
        # Full wheels contain QML image paths exceeding Win32 MAX_PATH. These
        # unused files must be removed too, without relying on a host setting.
        path.unlink()
    for path in sorted(qt.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    report["retained_files"] = [{"path": "runtime/Lib/site-packages/PySide6/" + name,
        "sha256": hashlib.sha256((qt / name).read_bytes()).hexdigest()} for name in report["kept"]]
    (package / "QT_RUNTIME_MANIFEST.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
