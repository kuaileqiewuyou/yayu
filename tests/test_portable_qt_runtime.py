"""Fail-closed packaging checks plus optional checks on real installed Qt PEs."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import struct

import pytest

from scripts.portable_qt_runtime import (
    QT_DLLS, QT_MODULES, PLUGINS, _guard, application_qt_imports,
    pe_imports, prune_qt_runtime, runtime_plan, _native_path,
)


def _pe(tmp_path: Path, *, delayed: bool = False) -> Path:
    """Small spec-shaped x64 PE containing a named import and terminator."""
    image = bytearray(1024)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x80)
    image[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HH", image, 0x84, 0x8664, 1)
    struct.pack_into("<H", image, 0x94, 240)
    struct.pack_into("<H", image, 0x98, 0x20B)
    struct.pack_into("<Q", image, 0x98 + 24, 0x140000000)
    directory = 13 if delayed else 1
    record = 32 if delayed else 20
    struct.pack_into("<II", image, 0x98 + 112 + directory * 8, 0x1000, record * 2)
    struct.pack_into("<IIII", image, 0x98 + 240 + 8, 512, 0x1000, 512, 512)
    values = (1, 0x1100, 0, 0, 0, 0, 0, 0) if delayed else (0, 0, 0, 0x1100, 0)
    struct.pack_into("<" + "I" * len(values), image, 512, *values)
    image[768:781] = b"KERNEL32.dll\0"
    target = tmp_path / "sample.dll"
    target.write_bytes(image)
    return target


@pytest.mark.parametrize("delayed", [False, True])
def test_reads_normal_and_delay_imports(tmp_path, delayed):
    assert pe_imports(_pe(tmp_path, delayed=delayed)) == {"kernel32.dll"}


@pytest.mark.parametrize("content", [b"", b"MZ", b"This is not a Windows DLL"])
def test_rejects_invalid_or_truncated_pe(tmp_path, content):
    path = tmp_path / "broken.dll"
    path.write_bytes(content)
    with pytest.raises(ValueError):
        pe_imports(path)


def test_import_string_rva_outside_sections_is_rejected(tmp_path):
    path = _pe(tmp_path)
    data = bytearray(path.read_bytes())
    struct.pack_into("<I", data, 512 + 12, 0xFFFF0000)
    path.write_bytes(data)
    with pytest.raises(ValueError, match="RVA"):
        pe_imports(path)


def test_new_application_qt_module_requires_audit(tmp_path):
    (tmp_path / "ui").mkdir()
    source = tmp_path / "ui/new.py"
    source.write_text("from PySide6.QtCharts import QChart\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unaudited.*QtCharts"):
        application_qt_imports(tmp_path)


def test_pyside_root_imports_and_runtime_packages_are_checked(tmp_path):
    (tmp_path / "tts").mkdir()
    (tmp_path / "tts/imports.py").write_text("from PySide6 import QtSvg\nimport PySide6.QtCore\n", encoding="utf-8")
    assert application_qt_imports(tmp_path) == {"QtCore", "QtSvg"}


def test_snapshot_tool_imports_do_not_expand_runtime(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/ui_snapshot.py").write_text("from PySide6.QtTest import QTest\n", encoding="utf-8")
    assert application_qt_imports(tmp_path) == set()


def test_refuses_development_venv_and_incomplete_package(tmp_path):
    with pytest.raises(ValueError, match="portable package"):
        _guard(tmp_path)
    package = tmp_path / "venv"
    (package / "runtime/Lib/site-packages/PySide6").mkdir(parents=True)
    (package / "portable_bootstrap.py").write_text("", encoding="utf-8")
    (package / "runtime/python.exe").write_bytes(b"")
    with pytest.raises(ValueError, match="virtual environment"):
        _guard(package)


def test_no_gpl_only_qt_module_is_eligible():
    assert {"qt6charts.dll", "qt6graphs.dll", "qt6quick3d.dll", "qt6datavisualization.dll"}.isdisjoint(QT_DLLS)
    assert QT_MODULES == {"QtCore", "QtGui", "QtWidgets", "QtNetwork", "QtSvg", "QtMultimedia"}
    assert all("qml" not in name.lower() and "webengine" not in name.lower() for name in PLUGINS)


def test_real_wheel_pe_imports_are_decoded():
    spec = importlib.util.find_spec("PySide6")
    if not spec or not spec.origin or os.name != "nt":
        pytest.skip("Windows PySide6 wheel is not installed")
    qt = Path(spec.origin).parent
    assert {"qt6core.dll", "qt6gui.dll", "qt6widgets.dll"} <= pe_imports(qt / "QtWidgets.pyd")
    assert "kernel32.dll" in pe_imports(qt / "Qt6Core.dll")
    ffmpeg = pe_imports(qt / "plugins/multimedia/ffmpegmediaplugin.dll")
    assert {"avcodec-61.dll", "avformat-61.dll", "avutil-59.dll", "swscale-8.dll", "swresample-5.dll"} <= ffmpeg


@pytest.fixture
def actual_package():
    value = os.environ.get("GALGAME_QT_TEST_PACKAGE")
    if not value:
        pytest.skip("Set GALGAME_QT_TEST_PACKAGE for full official-wheel dependency validation")
    return Path(value)


def test_full_real_pe_closure_contains_only_reviewed_qt_modules(actual_package):
    report = runtime_plan(actual_package)
    assert {name.lower() for name in report["qt_libraries"]} == QT_DLLS
    assert len(report["dependencies"]) >= 35
    assert {"avcodec-61.dll", "avformat-61.dll", "avutil-59.dll", "swscale-8.dll", "swresample-5.dll"} <= set(report["kept"])
    if "QtCharts.pyd" in report["removed"]:
        assert report["bytes_after"] < report["bytes_before"] / 3
    assert not any(name.lower().endswith(("opengl32sw.dll", "qt6quick3d.dll", "qt6graphs.dll")) for name in report["kept"])


def test_wrong_dependencies_target_is_rejected_before_mutation(actual_package, tmp_path):
    qt = actual_package / "runtime/Lib/site-packages/PySide6"
    before = (qt / "QtCore.pyd").stat()
    with pytest.raises(ValueError, match="Dependencies directory"):
        prune_qt_runtime(tmp_path, actual_package)
    assert (qt / "QtCore.pyd").stat() == before


@pytest.fixture
def small_package(tmp_path):
    package = tmp_path / "portable"
    qt = package / "runtime/Lib/site-packages/PySide6"
    qt.mkdir(parents=True)
    (package / "runtime/python.exe").write_bytes(b"")
    (package / "portable_bootstrap.py").write_text("", encoding="utf-8")
    (qt / "_config.py").write_text('version = "6.8.3"\n', encoding="utf-8")
    binary = _pe(tmp_path).read_bytes()
    for name in PLUGINS | {module + ".pyd" for module in QT_MODULES}:
        path = qt / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(binary)
    return package, qt


def test_unknown_dll_import_aborts_before_any_deletions(small_package):
    package, qt = small_package
    target = qt / "QtWidgets.pyd"
    target.write_bytes(target.read_bytes().replace(b"KERNEL32.dll\0", b"LIBRARYX.dll\0"))
    unused = qt / "Qt6Charts.dll"
    unused.write_bytes(b"unused")
    with pytest.raises(ValueError, match="Unresolved or unaudited DLL"):
        prune_qt_runtime(qt.parent, package)
    assert unused.read_bytes() == b"unused"
    assert not (package / "QT_RUNTIME_MANIFEST.json").exists()


@pytest.mark.skipif(os.name != "nt", reason="Win32 extended-path regression")
def test_long_unused_wheel_files_are_removed(small_package):
    package, qt = small_package
    native = _native_path(qt.resolve())
    # Ordinary is_file can return False above MAX_PATH, which previously left
    # long QML paths out of both deletion plans and published ZIP manifests.
    relative = "qml/QtQuick3D/" + ("long-folder-name/" * 12) + "unused-plugin.dll"
    extra = native / relative
    extra.parent.mkdir(parents=True)
    extra.write_bytes(b"not needed")
    assert len(str(extra)) > 260
    report = prune_qt_runtime(_native_path(qt.parent.resolve()), _native_path(package.resolve()))
    assert relative in report["removed"]
    assert not extra.exists()
    assert not (native / "qml").exists()


@pytest.mark.skipif(os.name != "nt", reason="Win32 extended-path regression")
def test_normal_and_extended_package_paths_give_same_real_dependency_closure(actual_package):
    normal = runtime_plan(actual_package)
    extended = runtime_plan(_native_path(actual_package.resolve()))
    assert normal == extended
