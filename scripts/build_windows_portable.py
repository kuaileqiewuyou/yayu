"""Build a clean Windows x64 ZIP from a committed tree, never a local profile.

Run with an installed Windows Python containing pip. Dependencies are downloaded
as wheels from PyPI and vendored alongside the official embedded interpreter.
The resulting application needs neither an installed Python nor pip.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import urllib.request
import zipfile

if __package__:
    from .portable_license_sources import prepare_license_delivery
    from .portable_qt_runtime import prune_qt_runtime
else:
    from portable_license_sources import prepare_license_delivery
    from portable_qt_runtime import prune_qt_runtime


PYTHON_VERSION = "3.13.12"
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
PYTHON_SHA256 = "76f238f606250c87c6beac75dccd35ee99070a13490555936abb6cb64ecce3d0"
PACKAGE_ROOTS = ("asr/", "config/", "core/", "i18n/", "llm/", "plugins/", "sdk/", "t2i/", "tts/", "ui/")
CHARACTER_FILES = {"README.md", "character.yaml", "persona.md", "standing-neutral.png", "standing-wink.png", "standing-listening.png"}
ROOT_FILES = {"main.py", "webui_qt.py", "portable_bootstrap.py", "VERSION", "README.md", "THIRD_PARTY_NOTICES.md", "requirements.txt"}
LICENSE_FILES = {"licenses/Shinsekai-MIT.txt", "licenses/Yayu-Noncommercial.txt", "licenses/Yayu-LICENSE-SCOPE.md"}
SCRIPT_FILES = {"scripts/init_config.py", "scripts/windows_launcher.cs", "scripts/build_windows_launcher.ps1", "scripts/requirements-windows-portable.txt"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def filesystem_path(path: Path) -> Path:
    """Use Windows extended paths so traversal cannot silently omit long files."""
    path = path.absolute()
    value = str(path)
    if os.name == "nt" and not value.startswith("\\\\?\\"):
        value = "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value
        return Path(value)
    return path


def runtime_source_path(path: str) -> bool:
    """Explicit public allowlist; no user configuration or imported resources."""
    if path in ROOT_FILES | SCRIPT_FILES | LICENSE_FILES or path == "docs/windows-portable.md":
        return True
    if path.startswith(PACKAGE_ROOTS):
        return Path(path).suffix.lower() in {".py", ".json", ".yaml", ".yml", ".txt", ".qss", ".svg", ".png", ".ico", ".ttf"}
    if path == "data/character_templates/default.txt":
        return True
    if path.startswith("data/config/"):
        return path.endswith(".example.yaml") and PurePosixPath(path).name != "characters.example.yaml"
    if path.startswith("data/characters/xiaoya/"):
        return path.removeprefix("data/characters/xiaoya/") in CHARACTER_FILES
    return False


def extract_runtime_source(source_zip: Path, package: Path) -> None:
    """Select public files and retain the exact project license in an old-updater-safe path."""
    with zipfile.ZipFile(source_zip) as archive:
        # v1.0.4 only accepts known root files. Keep LICENSE in the source tree,
        # with an identical copy under its existing allowed licenses/ directory.
        for name in LICENSE_FILES | {"LICENSE"}:
            if name not in archive.namelist() or not archive.read(name).strip():
                raise ValueError("Missing or empty distribution license: " + name)
        if archive.read("LICENSE") != archive.read("licenses/Yayu-Noncommercial.txt"):
            raise ValueError("Project license copy differs from root LICENSE")
        for entry in archive.infolist():
            if entry.is_dir() or not runtime_source_path(entry.filename):
                continue
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe source archive member")
            target = package / entry.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(entry))


def run(command: list[str], **kwargs) -> None:
    subprocess.run(command, check=True, **kwargs)


def remove_vendor_bytecode(dependencies: Path, package: Path) -> None:
    """Drop wheel-supplied caches when the portable source module is present."""
    assert dependencies.resolve().is_relative_to(package.resolve())
    for path in dependencies.rglob("*.pyc"):
        if path.parent.name == "__pycache__":
            source = path.parent.parent / (path.name.split(".", 1)[0] + ".py")
        else:
            source = path.with_suffix(".py")
        if not source.is_file():
            raise ValueError("Bytecode-only dependency module: " + str(path.relative_to(package)))
        path.unlink()
    for folder in sorted(dependencies.rglob("__pycache__"), key=lambda path: len(path.parts), reverse=True):
        if not any(folder.iterdir()):
            folder.rmdir()


def build(source: Path, ref: str, work: Path, output: Path) -> Path:
    if sys.platform != "win32":
        raise RuntimeError("Build on 64-bit Windows with Python 3.13 and pip.")
    if sys.version_info[:2] != (3, 13) or sys.maxsize <= 2**32:
        raise RuntimeError("The build interpreter must be 64-bit Python 3.13.")
    git = ["git", "-c", "safe.directory=" + source.as_posix(), "-C", str(source)]
    commit = subprocess.check_output(git + ["rev-parse", "--verify", ref + "^{commit}"], text=True).strip()
    version = subprocess.check_output(git + ["show", commit + ":VERSION"], text=True).strip()
    name = f"Yayu-{version}-windows-x64"
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    normal_package = work / (name + "-" + commit[:8]) / name
    package = filesystem_path(normal_package)
    if package.exists():
        raise FileExistsError(f"Choose a fresh work directory; refusing to overwrite {package}")
    package.mkdir(parents=True)

    source_zip = normal_package.parent / "committed-source.zip"
    run(git + ["archive", "--format=zip", "--output", str(source_zip), commit])
    extract_runtime_source(source_zip, package)
    # Always synthesize a blank API default. Even a committed local override
    # must never become part of a portable application.
    (package / "data/config/api.yaml").write_text("llm_provider: custom\nllm_api_key: {}\nllm_model: {}\nllm_base_url: ''\ntts_provider: none\nt2i_provider: none\n", encoding="utf-8")

    embedded_zip = work / f"python-{PYTHON_VERSION}-embed-amd64.zip"
    if not embedded_zip.exists():
        print("Downloading official embedded Python", flush=True)
        with urllib.request.urlopen(PYTHON_URL, timeout=120) as response, embedded_zip.open("wb") as target:
            shutil.copyfileobj(response, target)
    if sha256(embedded_zip) != PYTHON_SHA256:
        raise ValueError("Official embedded Python SHA256 mismatch")
    runtime = package / "runtime"
    with zipfile.ZipFile(embedded_zip) as archive:
        archive.extractall(runtime)
    (runtime / "python313._pth").write_text("python313.zip\n.\nLib/site-packages\n..\n", encoding="utf-8")

    wheels = work / "wheels"
    wheels.mkdir(exist_ok=True)
    requirements = package / "scripts/requirements-windows-portable.txt"
    run([sys.executable, "-E", "-m", "pip", "--isolated", "--disable-pip-version-check", "download", "--only-binary=:all:", "--index-url", "https://pypi.org/simple", "--dest", str(wheels), "-r", str(requirements)])
    dependencies = runtime / "Lib/site-packages"
    run([sys.executable, "-E", "-m", "pip", "--isolated", "--disable-pip-version-check", "install", "--no-index", "--find-links", str(wheels), "--only-binary=:all:", "--no-compile", "--no-warn-script-location", "--target", str(dependencies), "-r", str(requirements)])
    # pip console wrappers embed the build interpreter path. The app never uses
    # these utilities; leave all distribution license/metadata files intact.
    for folder in (dependencies / "bin", dependencies / "Scripts"):
        if folder.is_dir():
            assert folder.resolve().is_relative_to(package.resolve())
            for path in folder.rglob("*"):
                if path.is_file():
                    path.unlink()
            for path in sorted(folder.rglob("*"), key=lambda item: len(item.parts), reverse=True):
                if path.is_dir():
                    path.rmdir()
            folder.rmdir()
    remove_vendor_bytecode(dependencies, package)
    qt_manifest = prune_qt_runtime(dependencies, package)
    license_delivery = prepare_license_delivery(package, work / "source-cache", output, version, {**qt_manifest, "source_commit": commit})

    run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(normal_package / "scripts/build_windows_launcher.ps1"), "-OutputDirectory", str(normal_package)])
    (package / "开始使用.txt").write_text(
        "芽语 / Yayu Windows 便携版\n\n"
        "1. 将整个文件夹解压到有写入权限的位置，不要在压缩包内直接打开。\n"
        "2. 双击 Yayu Settings.exe，配置自己的接口地址、API Key 和模型 ID，保存后关闭设置。\n"
        "3. 双击 Yayu.exe 打开聊天。无需安装 Python。\n"
        "4. 点击台词框左上角角色名，或从主页打开设置后点角色卡片的“使用此角色”。\n"
        "   立绘与设定同步切换，每个角色保留自己的会话和记忆；回复中先点“停止”再切换。\n\n"
        "5. 后续在“系统设置 → 软件更新”检查和安装新版，自动备份并保留原数据。\n"
        "首次启动会在 data 内创建自己的配置和聊天数据。发布包不含 API Key、私人配置或聊天记录。\n"
        "请始终保留 runtime 和其它文件夹，两个 EXE 不能单独使用。更新备份位于安装目录旁的 .yayu-updates。\n"
        "LLM/Edge TTS 需要网络和自己的服务配置；GPT-SoVITS、ComfyUI、MCP 服务需单独准备。\n"
        "Windows 10 1809 及以上 / Windows 11，64 位。故障日志位于 logs。\n"
        "详细说明：docs/windows-portable.md\n\n"
        "授权：有权由本项目授权的自有内容采用 PolyForm Noncommercial 1.0.0。\n"
        "许可全文：licenses/Yayu-Noncommercial.txt；适用范围：licenses/Yayu-LICENSE-SCOPE.md。\n"
        "第三方组件和素材继续遵守各自原许可，详见 THIRD_PARTY_NOTICES.md。\n", encoding="utf-8-sig")
    (package / "THIRD_PARTY_NOTICES.txt").write_text(
        "Yayu-owned content, where authorized by the project, is covered by PolyForm Noncommercial 1.0.0.\n"
        "Project terms: licenses/Yayu-Noncommercial.txt; scope and exceptions: licenses/Yayu-LICENSE-SCOPE.md.\n"
        "Third-party components are distributed under their own licenses. Retained binaries are unmodified; unused Qt modules are omitted.\n"
        "Shinsekai MIT-era implementation: THIRD_PARTY_NOTICES.md and licenses/Shinsekai-MIT.txt.\n"
        "CPython: Python Software Foundation license, runtime/LICENSE.txt.\n"
        f"CPython source: https://www.python.org/ftp/python/{PYTHON_VERSION}/Python-{PYTHON_VERSION}.tar.xz\n"
        "PySide6 / shiboken6 / Qt 6.8.3 and FFmpeg: full license terms and notices in licenses/qt/.\n"
        "These shared libraries remain separate and may be replaced with compatible builds; see licenses/qt/LIBRARY_REPLACEMENT.md.\n"
        f"Corresponding third-party sources: {license_delivery['url']}\n"
        f"Source archive SHA256: {license_delivery['sha256']}\n"
        "Font: ui/assets/fonts/OFL.txt and SOURCE.txt.\n"
        "Other package licenses: runtime/Lib/site-packages/*.dist-info/licenses, LICENSE*, or METADATA.\n", encoding="utf-8")
    distributions = []
    for wheel in sorted(wheels.glob("*.whl")):
        distributions.append({"wheel": wheel.name, "sha256": sha256(wheel)})
    info = {"version": version, "source_commit": commit, "platform": "windows-x64", "python": PYTHON_VERSION, "python_archive_sha256": PYTHON_SHA256, "wheels": distributions, "qt_runtime": qt_manifest, "third_party_sources": license_delivery}
    (package / "BUILD_INFO.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    files = sorted(path for path in package.rglob("*") if path.is_file())
    forbidden = [path.relative_to(package).as_posix() for path in files if "__pycache__" in path.parts or path.suffix == ".pyc"]
    if forbidden:
        raise ValueError("Unexpected generated bytecode in package: " + repr(forbidden[:10]))
    manifest = [{"path": path.relative_to(package).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)} for path in files]
    (package / "PACKAGE_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    zip_path = output / (name + ".zip")
    if zip_path.exists():
        raise FileExistsError(f"Refusing to replace {zip_path}")
    print("Creating portable ZIP", flush=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for path in sorted(package.rglob("*")):
            if path.is_file():
                archive.write(path, (Path(name) / path.relative_to(package)).as_posix())
    source_zip = output / license_delivery["asset"]
    if not source_zip.is_file() or sha256(source_zip) != license_delivery["sha256"]:
        raise ValueError("Corresponding source archive is missing or its SHA256 changed")
    (output / "SHA256SUMS.txt").write_text(
        sha256(zip_path) + "  " + zip_path.name + "\n" +
        license_delivery["sha256"] + "  " + source_zip.name + "\n", encoding="ascii")
    print(json.dumps({"zip": str(zip_path), "bytes": zip_path.stat().st_size, "sha256": sha256(zip_path), "source_commit": commit}), flush=True)
    return zip_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--work-dir", type=Path, required=True, help="A new build directory; an NTFS volume is recommended.")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    build(args.source_dir.resolve(), args.ref, args.work_dir.resolve(), args.output_dir.resolve())
