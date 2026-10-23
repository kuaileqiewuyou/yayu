"""Source-delivery safeguards use tiny fixtures and never make network calls."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile

import pytest

from scripts import portable_license_sources as delivery


def make_tar(path: Path, files: dict[str, bytes]) -> None:
    with tarfile.open(path, "w") as archive:
        for name, content in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))


def test_modified_cached_source_is_rejected_without_download(tmp_path, monkeypatch):
    (tmp_path / "source.tar.xz").write_bytes(b"tampered")
    source = {"archive": "source.tar.xz", "url": "https://invalid.example/source", "sha256": hashlib.sha256(b"original").hexdigest()}
    monkeypatch.setattr(delivery.urllib.request, "urlopen", lambda *a, **k: pytest.fail("must not download over an existing archive"))
    with pytest.raises(ValueError, match="Cached source SHA256 mismatch"):
        delivery.verified_source(tmp_path, source)


def test_downloaded_source_hash_is_checked_before_cache_commit(tmp_path, monkeypatch):
    source = {"archive": "source.tar.xz", "url": "https://invalid.example/source", "sha256": hashlib.sha256(b"original").hexdigest()}
    monkeypatch.setattr(delivery.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"wrong download"))
    with pytest.raises(ValueError, match="Downloaded source SHA256 mismatch"):
        delivery.verified_source(tmp_path, source)
    assert not (tmp_path / "source.tar.xz").exists()


def test_attribution_license_file_is_preserved_even_with_unusual_name(tmp_path):
    archive = tmp_path / "source.tar"
    original = b"Copyright Original Author\nPermission to copy...\n"
    make_tar(archive, {"module/src/qt_attribution.json": json.dumps({"LicenseFile": "terms.dat"}).encode(),
                       "module/src/terms.dat": original, "module/src/code.c": b"code"})
    count = delivery.extract_notices(archive, tmp_path / "notices")
    assert count == 2
    assert (tmp_path / "notices/module/src/terms.dat").read_bytes() == original
    assert not (tmp_path / "notices/module/src/code.c").exists()


@pytest.mark.parametrize("member", ["../outside", "/absolute", "C:/drive", "module/../../outside", "module\\outside"])
def test_archive_paths_cannot_escape_notice_directory(tmp_path, member):
    archive = tmp_path / "bad.tar"
    make_tar(archive, {member: b"untrusted"})
    with pytest.raises(ValueError, match="Unsafe upstream archive member"):
        delivery.extract_notices(archive, tmp_path / "notices")


def test_attribution_path_cannot_escape_source_root(tmp_path):
    archive = tmp_path / "source.tar"
    make_tar(archive, {"module/qt_attribution.json": b'{"LicenseFile":"../../outside"}'})
    with pytest.raises(ValueError, match="Unsafe upstream archive member"):
        delivery.extract_notices(archive, tmp_path / "notices")


def test_unmapped_qt_module_is_rejected_before_source_delivery(tmp_path):
    pyside = tmp_path / "runtime/Lib/site-packages/PySide6"
    pyside.mkdir(parents=True)
    (pyside / "_config.py").write_text('version = "6.8.3"\n')
    for name in delivery.QT_COMPONENTS:
        (pyside / name).touch()
    (pyside / "Qt6Charts.dll").touch()
    with pytest.raises(ValueError, match="Qt binary/source scope changed"):
        delivery.runtime_evidence(tmp_path)


def test_missing_attribution_license_stops_delivery(tmp_path):
    archive = tmp_path / "source.tar"
    make_tar(archive, {"module/qt_attribution.json": b'{"LicenseFile":"missing.txt"}'})
    with pytest.raises(ValueError, match="Missing attributed license file"):
        delivery.extract_notices(archive, tmp_path / "notices")


def test_yayu_source_asset_and_notices_use_renamed_release_without_changing_archives(tmp_path, monkeypatch):
    package = tmp_path / "app"
    package.mkdir()
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    sources = []
    paths = {}
    for component, files in (
        ("qtbase", {"qtbase/LICENSES/GPL-3.0-only.txt": b"original GPL 3",
                    "qtbase/LICENSES/LGPL-3.0-only.txt": b"original LGPL 3",
                    "qtbase/LICENSES/GPL-2.0-only.txt": b"original GPL 2"}),
        ("FFmpeg", {"ffmpeg/COPYING.LGPLv2.1": b"original LGPL 2.1"}),
        ("qt5-build-scripts", {"qt5/LICENSE.txt": b"original upstream notice"}),
    ):
        archive = fixtures / (component + ".tar")
        make_tar(archive, files)
        paths[archive.name] = archive
        sources.append({"component": component, "archive": archive.name,
                        "sha256": delivery.sha256(archive)})
    monkeypatch.setattr(delivery, "SOURCE_ARCHIVES", tuple(sources))
    monkeypatch.setattr(delivery, "verified_source", lambda cache, source: paths[source["archive"]])
    monkeypatch.setattr(delivery, "runtime_evidence", lambda root: {"binaries": []})

    result = delivery.prepare_license_delivery(
        package, tmp_path / "cache", tmp_path / "output", "1.0.2", {"source_commit": "test-commit"})

    expected_root = "Yayu-1.0.2-third-party-sources"
    assert result["asset"] == expected_root + ".zip"
    assert result["url"] == (
        "https://github.com/kuaileqiewuyou/yayu/releases/download/v1.0.2/" + result["asset"])
    licenses = package / "licenses/qt"
    assert (licenses / "LGPL-3.0.txt").read_bytes() == b"original LGPL 3"
    replacement = (licenses / "LIBRARY_REPLACEMENT.md").read_text(encoding="utf-8")
    assert "Yayu.exe and Yayu Settings.exe" in replacement
    assert result["url"] in replacement
    assert json.loads((licenses / "RUNTIME_BINARIES.json").read_text())["application_source_commit"] == "test-commit"
    with zipfile.ZipFile(tmp_path / "output" / result["asset"]) as archive:
        assert all(name.startswith(expected_root + "/") for name in archive.namelist())
        for source in sources:
            assert archive.read(expected_root + "/archives/" + source["archive"]) == paths[source["archive"]].read_bytes()
