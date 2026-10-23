"""Deliver fixed-version Qt/PySide/FFmpeg source and notices with a portable ZIP.

Source archives are downloaded from official upstream projects, verified against
fixed SHA256 values, and shipped unchanged as a separate Release asset. Nothing
is read from a user's application configuration, history, or environment.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import tarfile
import urllib.request
import zipfile


QT_VERSION = "6.8.3"
QT5_COMMIT = "bab1fecd556ea561c4a89686293116741acfa1b4"
RELEASE_REPOSITORY = "kuaileqiewuyou/yayu"
QT_BASE_URL = "https://download.qt.io/archive/qt/6.8/6.8.3/submodules/"
FFMPEG_CONFIGURATION = (
    "--prefix=installed --disable-programs --disable-doc --disable-debug "
    "--enable-network --disable-lzma --enable-pic --disable-vulkan "
    "--disable-v4l2-m2m --disable-decoder=truemotion1 --toolchain=msvc "
    "--enable-shared --disable-static"
)
QT_COMPONENTS = {
    "Qt6Core.dll": "qtbase", "Qt6Gui.dll": "qtbase",
    "Qt6Widgets.dll": "qtbase", "Qt6Network.dll": "qtbase",
    "Qt6Svg.dll": "qtsvg", "Qt6Multimedia.dll": "qtmultimedia",
}
PLUGIN_COMPONENTS = {
    "qsvgicon.dll": "qtsvg", "qsvg.dll": "qtsvg",
    "qgif.dll": "qtbase", "qico.dll": "qtbase", "qjpeg.dll": "qtbase",
    "qtiff.dll": "qtimageformats", "qwebp.dll": "qtimageformats",
    "ffmpegmediaplugin.dll": "qtmultimedia", "windowsmediaplugin.dll": "qtmultimedia",
    "qnetworklistmanager.dll": "qtbase", "qwindows.dll": "qtbase",
    "qmodernwindowsstyle.dll": "qtbase", "qcertonlybackend.dll": "qtbase",
    "qschannelbackend.dll": "qtbase",
}
FFMPEG_DLLS = {"avcodec-61.dll", "avformat-61.dll", "avutil-59.dll",
               "swresample-5.dll", "swscale-8.dll"}
QT_HASHES = {
    "qtbase": "56001b905601bb9023d399f3ba780d7fa940f3e4861e496a7c490331f49e0b80",
    "qtsvg": "35eb516460f00f264eb504baa253432384351cf23fb9980a5857190e8deef438",
    "qtmultimedia": "32e82307d783172a3b984cc3c47c5e4e8b819cee3cbfc702c7012c47f15f6b01",
    "qtimageformats": "049bfb99845e4801672aca07c3c4fc4c140f932a3a33faa899419579e33ef1c8",
    "qttranslations": "c3c61d79c3d8fe316a20b3617c64673ce5b5519b2e45535f49bee313152fa531",
}
SOURCE_ARCHIVES = tuple(
    {"component": component, "version": QT_VERSION,
     "archive": f"{component}-everywhere-src-{QT_VERSION}.tar.xz",
     "url": QT_BASE_URL + f"{component}-everywhere-src-{QT_VERSION}.tar.xz",
     "sha256": digest, "checksum_url": QT_BASE_URL + f"{component}-everywhere-src-{QT_VERSION}.tar.xz.sha256"}
    for component, digest in QT_HASHES.items()
) + (
    {"component": "pyside-setup", "version": QT_VERSION,
     "archive": "pyside-setup-everywhere-src-6.8.3.tar.xz",
     "url": "https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.8.3-src/pyside-setup-everywhere-src-6.8.3.tar.xz",
     "sha256": "d2c896f7f1a6a7ea4c9f98cfe317272fd139703ddf612b86999f09e48aeef0e6",
     "checksum_url": "https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.8.3-src/pyside-setup-everywhere-src-6.8.3.tar.xz.sha256"},
    {"component": "FFmpeg", "version": "n7.1",
     "archive": "FFmpeg-n7.1.tar.gz",
     "url": "https://codeload.github.com/FFmpeg/FFmpeg/tar.gz/refs/tags/n7.1",
     "sha256": "7ddad2d992bd250a6c56053c26029f7e728bebf0f37f80cf3f8a0e6ec706431a",
     "qt_provisioning_sha1": "f008a93710a7577e3f85a90f4b632cc615164712"},
    {"component": "qt5-build-scripts", "version": QT_VERSION,
     "commit": QT5_COMMIT, "archive": "qt5-build-scripts-6.8.3.tar.gz",
     "url": f"https://codeload.github.com/qt/qt5/tar.gz/{QT5_COMMIT}",
     "sha256": "bf419eef0009e5fa68dc698bb2a7f18af189e65122ea4bd9a531b521d82be4ad"},
)


def sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def verified_source(cache: Path, source: dict) -> Path:
    """Cache official archives; never accept a changed or partial archive."""
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / source["archive"]
    if not target.exists():
        partial = target.with_suffix(target.suffix + ".part")
        request = urllib.request.Request(source["url"], headers={"User-Agent": "Yayu-source-delivery/1.0"})
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        if sha256(partial) != source["sha256"]:
            raise ValueError("Downloaded source SHA256 mismatch: " + source["archive"])
        partial.replace(target)
    if sha256(target) != source["sha256"]:
        raise ValueError("Cached source SHA256 mismatch: " + source["archive"])
    if "qt_provisioning_sha1" in source:
        if hashlib.sha1(target.read_bytes()).hexdigest() != source["qt_provisioning_sha1"]:
            raise ValueError("FFmpeg archive differs from the official Qt provisioning source")
    return target


def safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts or ":" in name or "\\" in name:
        raise ValueError("Unsafe upstream archive member: " + name)
    return path


def extract_notices(archive_path: Path, destination: Path) -> int:
    """Copy original licenses, copyright records and referenced attribution files.

    This is deliberately a superset of notices: source archives also contain
    examples, tests and optional platform code that are not in the runtime.
    The entire unmodified archive remains available in the source asset.
    """
    with tarfile.open(archive_path) as archive:
        members = {item.name: item for item in archive.getmembers() if item.isfile()}
        for name in members:
            safe_member(name)
        selected = set()
        for name in members:
            path = PurePosixPath(name)
            upper = path.name.upper()
            if ("LICENSES" in path.parts or any(word in upper for word in ("LICENSE", "LICENCE", "COPYING", "COPYRIGHT", "NOTICE"))
                    or path.name == "qt_attribution.json"):
                selected.add(name)
            if path.name != "qt_attribution.json":
                continue
            # Qt's own attribution reader accepts literal control characters in
            # some upstream descriptions; retain the original bytes unchanged.
            records = json.loads(archive.extractfile(members[name]).read(), strict=False)
            for record in records if isinstance(records, list) else [records]:
                files = record.get("LicenseFile", [])
                for license_file in files if isinstance(files, list) else [files]:
                    resolved = posixpath.normpath(str(path.parent / license_file))
                    safe_member(resolved)
                    if resolved not in members:
                        raise ValueError("Missing attributed license file: " + resolved)
                    selected.add(resolved)
        for name in sorted(selected):
            relative = safe_member(name)
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(members[name]).read())
    return len(selected)


def read_archive_file(path: Path, suffix: str) -> bytes:
    with tarfile.open(path) as archive:
        selected = [member for member in archive.getmembers() if member.isfile() and member.name.endswith(suffix)]
        if len(selected) != 1:
            raise ValueError("Expected one upstream file: " + suffix)
        return archive.extractfile(selected[0]).read()


def runtime_evidence(package: Path) -> dict:
    pyside = package / "runtime/Lib/site-packages/PySide6"
    if not pyside.is_dir():
        raise ValueError("Qt runtime missing")
    config = (pyside / "_config.py").read_text(encoding="utf-8")
    if not re.search(r'^version = [\'"]6\.8\.3[\'"]$', config, re.MULTILINE):
        raise ValueError("This source lock only supports PySide/Qt 6.8.3")
    actual_qt = {path.name for path in pyside.rglob("Qt6*.dll")}
    if actual_qt != set(QT_COMPONENTS):
        raise ValueError("Qt binary/source scope changed: " + repr(sorted(actual_qt)))
    actual_plugins = {path.name for path in (pyside / "plugins").rglob("*.dll")}
    if actual_plugins != set(PLUGIN_COMPONENTS):
        raise ValueError("Qt plugin/source scope changed: " + repr(sorted(actual_plugins)))
    actual_ffmpeg = {path.name for path in pyside.glob("*.dll") if re.match(r"(?:avcodec|avformat|avutil|swresample|swscale)-", path.name)}
    if actual_ffmpeg != FFMPEG_DLLS:
        raise ValueError("Expected the five source-matched FFmpeg 7.1 DLLs")
    evidence = []
    for path in sorted(pyside.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".dll", ".pyd", ".qm"}:
            continue
        record = {"path": path.relative_to(package).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)}
        if path.name in FFMPEG_DLLS:
            data = path.read_bytes()
            # swscale omits FFmpeg's common banner but retains the exact n7.1
            # source-tree tag and the same exported build configuration.
            matching_version = b"FFmpeg version 7.1\0" in data or (
                path.name == "swscale-8.dll" and b"FFmpeg-n7.1" in data)
            if not matching_version or FFMPEG_CONFIGURATION.encode() + b"\0" not in data:
                raise ValueError("FFmpeg binary does not match the supplied source/configuration: " + path.name)
            if b"LGPL version 2.1 or later" not in data:
                raise ValueError("Unexpected FFmpeg license variant: " + path.name)
            record.update(component="FFmpeg", version="7.1", configuration=FFMPEG_CONFIGURATION, license="LGPL-2.1-or-later")
        elif path.name in QT_COMPONENTS:
            record.update(component=QT_COMPONENTS[path.name], version=QT_VERSION)
        elif path.name in PLUGIN_COMPONENTS:
            record.update(component=PLUGIN_COMPONENTS[path.name], version=QT_VERSION)
        elif path.suffix == ".pyd" or path.name == "pyside6.abi3.dll":
            record.update(component="pyside-setup", version=QT_VERSION)
        elif path.suffix == ".qm":
            record.update(component="qttranslations", version=QT_VERSION)
        evidence.append(record)
    shiboken = package / "runtime/Lib/site-packages/shiboken6"
    for path in sorted(shiboken.glob("*")):
        if path.is_file() and path.suffix in {".dll", ".pyd"}:
            evidence.append({"path": path.relative_to(package).as_posix(), "bytes": path.stat().st_size,
                             "sha256": sha256(path), "component": "pyside-setup", "version": QT_VERSION})
    return {"pyside_wheel_build_configuration": config, "qt_version": QT_VERSION,
            "ffmpeg_configuration": FFMPEG_CONFIGURATION, "binaries": evidence,
            "modifications": "No changes to the upstream shared libraries; unused modules, tools and plugins are omitted."}


def replacement_instructions(asset: str, url: str) -> str:
    return f"""# Qt / PySide6 / FFmpeg: library replacement

The application uses separate shared libraries, without signature checks or a
device lock that blocks modified libraries. You may modify these libraries and
reverse engineer this application to debug those modifications as permitted by
the applicable LGPL. Nothing in the application's notices restricts those rights.

1. Close Yayu.exe and Yayu Settings.exe, then back up the complete portable folder
   and your data.
2. Download `{asset}` from the same Release: {url}
   Check its hash against SOURCES.json and the Release SHA256SUMS.txt, then unpack
   the source ZIP and its archives. Original licenses remain inside each archive.
3. Build an ABI-compatible x64 release of Qt 6.8.3, PySide6/shiboken6 6.8.3, or
   FFmpeg 7.1. BUILDING.md provides commands and the original build configuration.
   Keep the Qt minor version, CPython ABI and MSVC runtime compatible. Rebuild
   PySide6 against your modified Qt if the exported ABI changes.
4. Replace the relevant DLLs and plugins under `runtime/Lib/site-packages/PySide6`.
   PySide bindings are `Qt*.pyd` and `pyside6.abi3.dll`; shiboken files are in
   `runtime/Lib/site-packages/shiboken6`. Replace a coherent compatible set,
   including matching image/media/platform plugins. FFmpeg uses avcodec-61.dll,
   avformat-61.dll, avutil-59.dll, swresample-5.dll and swscale-8.dll.
5. Start either EXE normally. These launchers use the adjacent runtime and do not
   verify a vendor signature or reject a modified library. Replacing libraries
   requires no activation, app-store permission or vendor installation key.
   To diagnose loading, start `runtime/python.exe -E -u portable_bootstrap.py`
   from the portable root; add `--settings` for settings. Copy your modified
   libraries into a clean portable copy when testing, to protect your own data.

These are dynamic libraries, not statically linked application object files.
All shipped application Python sources and launcher/bootstrap sources are in
the portable folder. No application relinking step or private signing key is
needed. The source ZIP contains complete original component source archives,
not merely links to upstream downloads. It is supplied at no extra charge
through the same Release and access mechanism as the executable distribution.
"""


def building_instructions() -> str:
    return f"""# Building the supplied libraries

## Scope and provenance

This asset carries unmodified complete release archives for Qt 6.8.3 (qtbase,
qtsvg, qtmultimedia, qtimageformats, qttranslations), PySide6/shiboken6 6.8.3 and
FFmpeg n7.1. Their SHA256 values and official origins are in SOURCE_ARCHIVES.json.
qt5-build-scripts is Qt's v6.8.3 supermodule commit {QT5_COMMIT}, including
the original COIN provisioning/build scripts. Its submodule placeholders do not
replace component source: all runtime component source archives are also here.
No upstream library was patched by this application. Runtime pruning removes
unused files; the component archives retain their optional source, tests,
examples, configuration/build scripts and embedded third-party source/notices.

RUNTIME_BINARIES.json records the actual distributed libraries and file hashes,
the PySide wheel's original _config.py and the FFmpeg configuration embedded in
all five distributed FFmpeg DLLs. The FFmpeg archive's SHA1 also matches the
official Qt COIN script, `coin/provisioning/common/windows/install-ffmpeg.ps1`.
The PyPI wheels are upstream-built; we did not rebuild them and do not claim
byte-for-byte reproduction. The commands below build compatible modified
libraries. For all original CI platform options inspect the supplied qt5 COIN
configuration and PySide `coin_build_instructions.py`, `build_scripts/`,
`setup.py`, `create_wheels.py` and `sources/*/CMakeLists.txt`.

## Prerequisites

Use an x64 MSVC developer shell with the Windows SDK, CMake 3.22+, Ninja and
Python. Qt 6.8 supports the MSVC 2022 x64 toolchain. For CPython extension builds
install x64 CPython 3.13 (including headers/import libraries) and use matching
release builds. Install a suitable LLVM/libclang build for Shiboken's generator
and set LLVM_INSTALL_DIR. These are standard development tools, not bundled
runtime libraries. FFmpeg's MSVC build also needs an MSYS2 shell, make, perl and
NASM in PATH. See the supplied upstream installation/building documents and
configure --help for exact optional tooling. Build from a writable source tree.

## FFmpeg 7.1 (unmodified upstream MSVC shared build)

Unpack FFmpeg-n7.1.tar.gz. In MSYS2 with the x64 MSVC environment inherited:

```sh
mkdir build-msvc && cd build-msvc
../configure {FFMPEG_CONFIGURATION}
make -j8
make install
```

The full configuration above is extracted from the shipped DLLs and agrees
with Qt's supplied provisioning script/shared default options. GPL and nonfree
features are not enabled. FFmpeg is supplied under LGPL 2.1 or later. Rename
the MSVC import-library `lib*.a` files to the corresponding `*.lib` when needed
by Qt, as in the supplied original Qt install-ffmpeg.ps1. These are build
import libraries, distinct from the five runtime DLLs. No external codec source
is fetched by these options; source for enabled built-in codecs is in FFmpeg.

## Qt 6.8.3 shared libraries

Unpack each Qt module archive. Configure/build qtbase first in its own build
directory; use forward slashes and substitute your own absolute paths:

```bat
cmake -S C:/src/qtbase-everywhere-src-6.8.3 -B C:/build/qtbase -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=C:/build/qt-install -DBUILD_SHARED_LIBS=ON -DQT_BUILD_TESTS=OFF -DQT_BUILD_EXAMPLES=OFF
cmake --build C:/build/qtbase --parallel 8
cmake --install C:/build/qtbase
```

Configure/build/install qtsvg, qtimageformats and qtmultimedia in separate build
directories against that installation. For example:

```bat
cmake -S C:/src/qtsvg-everywhere-src-6.8.3 -B C:/build/qtsvg -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=C:/build/qt-install -DCMAKE_INSTALL_PREFIX=C:/build/qt-install -DQT_BUILD_TESTS=OFF -DQT_BUILD_EXAMPLES=OFF
cmake --build C:/build/qtsvg --parallel 8
cmake --install C:/build/qtsvg
```

For qtmultimedia also pass `-DFFMPEG_DIR=C:/src/FFmpeg-n7.1/build-msvc/installed`
and enable its FFmpeg and Windows media features if automatic detection is not
available; consult `configure.cmake` in the supplied source. Keep both backend
plugins for existing audio-format support. Qt's third-party zlib, PNG, JPEG,
FreeType/other font sources are inside qtbase; TIFF and WebP are inside
qtimageformats. Original third-party modifications and build scripts are part
of these complete module archives. QtNetwork uses the Windows Schannel plugin;
no separate OpenSSL DLL, ICU DLL, Chromium or software OpenGL DLL is shipped in
the pruned PySide runtime. QtTranslations carries original TS/QM source; its
`translations/qtbase_zh_CN.ts` and `qtmultimedia_zh_CN.ts` correspond to shipped
Chinese translations. Changing translations is optional; build them with the
compatible Qt lrelease development tool or keep the original QM data.

## PySide6 / shiboken6 6.8.3

Unpack pyside-setup-everywhere-src-6.8.3.tar.xz, install the development
requirements from that tree into a build virtual environment, set
LLVM_INSTALL_DIR, and run from its source root:

```bat
python -m pip install -r requirements.txt
python setup.py build --qtpaths=C:/build/qt-install/bin/qtpaths.exe --ignore-git --parallel=8 --module-subset=Core,Gui,Widgets,Network,Svg,Multimedia
python create_wheels.py --build-dir=C:/path/to/pyside-build --no-examples
```

Find the actual build directory produced by setup.py rather than copying the
placeholder above. Use `python setup.py --help` and the supplied source
documentation for build-tool version and packaging options. Extract matching
wheel packages into the portable runtime or copy the matching PySide6 and
shiboken6 binaries. The app needs six Python Qt bindings; installing additional
Qt modules does not make them part of this release. The original Qt/PySide
source documentation is included in the corresponding archives.

## Installation and verification

Follow LIBRARY_REPLACEMENT.md. No application relinking, private signing key,
DRM change or vendor activation is required. MSVC/Windows system libraries
remain their respective proprietary/system components; this source asset does
not misrepresent them as Qt/GNU-licensed code. Retained Python package metadata
in the application identifies other dependencies under their own licenses.
"""


def prepare_license_delivery(package: Path, source_cache: Path, output: Path,
                             version: str, qt_manifest: dict | None = None) -> dict:
    """Write app notices and a separate complete corresponding-source asset."""
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-.][A-Za-z0-9]+)*", version):
        raise ValueError("Invalid release version")
    package, source_cache, output = Path(package), Path(source_cache), Path(output)
    asset = f"Yayu-{version}-third-party-sources.zip"
    url = f"https://github.com/{RELEASE_REPOSITORY}/releases/download/v{version}/{asset}"
    output.mkdir(parents=True, exist_ok=True)
    asset_path = output / asset
    if asset_path.exists():
        raise FileExistsError("Refusing to replace an existing source asset")
    evidence = runtime_evidence(package)
    if qt_manifest and "source_commit" in qt_manifest:
        evidence["application_source_commit"] = qt_manifest["source_commit"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        archives = list(pool.map(lambda item: verified_source(source_cache, item), SOURCE_ARCHIVES))
    licenses = package / "licenses/qt"
    licenses.mkdir(parents=True, exist_ok=True)
    components = []
    for item, path in zip(SOURCE_ARCHIVES, archives):
        count = extract_notices(path, licenses / "upstream")
        components.append({**item, "bytes": path.stat().st_size, "notice_files": count})
    qtbase_archive = archives[0]
    ffmpeg_archive = archives[-2]
    for name, origin, suffix in (
        ("GPL-3.0.txt", qtbase_archive, "/LICENSES/GPL-3.0-only.txt"),
        ("LGPL-3.0.txt", qtbase_archive, "/LICENSES/LGPL-3.0-only.txt"),
        ("GPL-2.0.txt", qtbase_archive, "/LICENSES/GPL-2.0-only.txt"),
        ("LGPL-2.1.txt", ffmpeg_archive, "/COPYING.LGPLv2.1"),
    ):
        (licenses / name).write_bytes(read_archive_file(origin, suffix))
    (licenses / "BUILDING.md").write_text(building_instructions(), encoding="utf-8")
    (licenses / "LIBRARY_REPLACEMENT.md").write_text(replacement_instructions(asset, url), encoding="utf-8")
    (licenses / "NOTICE.md").write_text(
        "# Qt, PySide6, Shiboken and FFmpeg\n\n"
        "This distribution uses Qt/PySide6/Shiboken 6.8.3 shared libraries under LGPLv3, "
        "and FFmpeg 7.1 under LGPLv2.1 or later. Qt source headers retain The Qt Company "
        "Ltd. and the respective contributors' copyright notices. FFmpeg source files "
        "retain the FFmpeg developers' and respective contributors' notices. Exact "
        "copyright/attribution records and original licenses are retained under upstream/. "
        "This software is based in part on the work of the Independent JPEG Group and "
        "the FreeType Team. Their original notices and the PNG, TIFF and WebP notices "
        "remain in the corresponding upstream source/license directories.\n\n"
        "The complete LGPLv3, GPLv3, LGPLv2.1 and GPLv2 texts accompany this notice. "
        "GPL texts are included because LGPL incorporates or refers to them; their "
        "presence does not relicense the application as a whole. Individual bundled "
        "third-party components remain under their original licenses. The notice "
        "collection includes optional-source notices as a conservative superset.\n\n"
        f"Complete unmodified source archives: [{asset}]({url}), provided by this "
        "application distributor through the same Release as the binary at no extra "
        "charge. This is an actual corresponding-source download, not an upstream-only "
        "link or an unfulfilled written offer. SOURCE_ARCHIVES.json records fixed "
        "official origins and hashes. The application's licenses/qt/SOURCES.json "
        "records this Release asset hash.\n\n"
        "BUILDING.md and LIBRARY_REPLACEMENT.md explain building and installing modified "
        "compatible libraries. Users may modify the LGPL libraries and reverse engineer "
        "the application to debug such modifications as permitted by the LGPL. "
        "No license notice here limits those rights. Libraries were not modified; "
        "unused upstream modules, tools and plugins were omitted.\n", encoding="utf-8")
    (licenses / "SOURCE_ARCHIVES.json").write_text(json.dumps(components, indent=2), encoding="utf-8")
    (licenses / "RUNTIME_BINARIES.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    archive_root = f"Yayu-{version}-third-party-sources"
    with zipfile.ZipFile(asset_path, "x", allowZip64=True) as archive:
        for item, path in zip(SOURCE_ARCHIVES, archives):
            archive.write(path, archive_root + "/archives/" + item["archive"], compress_type=zipfile.ZIP_STORED)
        for path in sorted(licenses.rglob("*")):
            if path.is_file():
                archive.write(path, archive_root + "/" + path.relative_to(licenses).as_posix(), compress_type=zipfile.ZIP_DEFLATED)
        sums = "".join(item["sha256"] + "  archives/" + item["archive"] + "\n" for item in components)
        archive.writestr(archive_root + "/SHA256SUMS.txt", sums)
    result = {"asset": asset, "sha256": sha256(asset_path), "bytes": asset_path.stat().st_size,
              "url": url, "components": components}
    (licenses / "SOURCES.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
