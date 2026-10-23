"""The distribution must select public runtime files, never user data."""
import pytest
import os
from pathlib import Path
import zipfile

from scripts.build_windows_portable import (
    LICENSE_FILES, ROOT_FILES, SCRIPT_FILES, extract_runtime_source, filesystem_path,
    remove_vendor_bytecode, runtime_source_path,
)


@pytest.mark.parametrize("path", [
    "main.py", "portable_bootstrap.py", "THIRD_PARTY_NOTICES.md", "licenses/Shinsekai-MIT.txt",
    "licenses/Yayu-Noncommercial.txt", "licenses/Yayu-LICENSE-SCOPE.md", "config/schema.py", "core/runtime/chat_app.py",
    "ui/assets/fonts/OFL.txt", "ui/assets/fonts/ChillRoundF.ttf", "i18n/zh_CN.json",
    "data/config/system_config.example.yaml", "data/character_templates/default.txt",
    "data/characters/xiaoya/standing-neutral.png", "data/characters/xiaoya/persona.md",
])
def test_portable_contains_public_runtime_resources(path):
    assert runtime_source_path(path)


@pytest.mark.parametrize("path", [
    "data/config/api.yaml", "data/config/api.local.yaml", "data/config/characters.yaml",
    "data/config/system_config.yaml", "data/config/characters.example.yaml",
    "data/appdata/updates/github-token.dpapi", ".yayu-update-pending.json", ".yayu-app.lock",
    "data/chat_history/default.json", "data/memory/memory.sqlite3",
    "data/characters/private/character.yaml", "data/characters/xiaoya/source/reference.png",
    "data/characters/xiaoya/art-prompts.md", "data/avatars/personal.png",
    "data/backgrounds/private.png", "data/security/allowed-roots.json",
    "venv/Lib/site-packages/example.py", ".env", ".sandbox/anything.py",
    "logs/chat.log", "tests/test_ui_smoke.py",
    "licenses/private-credentials.txt", "licenses/local-notes.md", "LICENSE",
])
def test_portable_excludes_private_state_and_development_files(path):
    assert not runtime_source_path(path)


# Immutable path policy shipped in v1.0.4 (51144074d882e380e958c8ba6a627d54ea7d631f).
# A new updater's policy cannot make a ZIP readable by an already-installed one.
V1_0_4_PROGRAM_ROOTS = {
    "asr", "config", "core", "i18n", "llm", "plugins", "sdk", "t2i", "tts",
    "ui", "scripts", "runtime", "docs", "licenses",
}
V1_0_4_PROGRAM_FILES = {
    "main.py", "webui_qt.py", "portable_bootstrap.py", "VERSION", "README.md",
    "THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.txt", "requirements.txt",
    "Yayu.exe", "Yayu Settings.exe", "BUILD_INFO.json", "QT_RUNTIME_MANIFEST.json",
    "开始使用.txt",
}


def test_public_source_allowlist_remains_compatible_with_v1_0_4_updater():
    for path in ROOT_FILES | SCRIPT_FILES | LICENSE_FILES | {"docs/windows-portable.md"}:
        assert path in V1_0_4_PROGRAM_FILES or path.split("/", 1)[0] in V1_0_4_PROGRAM_ROOTS
    assert "LICENSE" not in ROOT_FILES
    assert {"licenses/Yayu-Noncommercial.txt", "licenses/Yayu-LICENSE-SCOPE.md"} <= LICENSE_FILES


def _license_source_archive(tmp_path, **changes):
    root = Path(__file__).resolve().parents[1]
    files = {name: (root / name).read_bytes() for name in LICENSE_FILES | {"LICENSE"}}
    files.update({"main.py": b"# public runtime", "licenses/private-credentials.txt": b"fictional private test data"})
    files.update(changes)
    archive_path = tmp_path / "source.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, content in files.items():
            if content is not None:
                archive.writestr(name, content)
    return archive_path, files


def test_license_delivery_preserves_complete_terms_and_scope_without_root_license(tmp_path):
    archive_path, files = _license_source_archive(tmp_path)
    output = tmp_path / "package"
    extract_runtime_source(archive_path, output)
    assert (output / "licenses/Yayu-Noncommercial.txt").read_bytes() == files["LICENSE"]
    assert b"PolyForm Noncommercial License 1.0.0" in files["LICENSE"]
    for name in LICENSE_FILES:
        assert (output / name).read_bytes() == files[name]
    assert not (output / "LICENSE").exists()
    assert not (output / "licenses/private-credentials.txt").exists()


@pytest.mark.parametrize("path,content", [
    ("licenses/Yayu-Noncommercial.txt", b"changed project terms"),
    ("licenses/Yayu-Noncommercial.txt", None),
    ("licenses/Yayu-LICENSE-SCOPE.md", b""),
    ("licenses/Shinsekai-MIT.txt", None),
    ("LICENSE", None),
])
def test_license_delivery_rejects_missing_scope_or_drifting_license(tmp_path, path, content):
    archive_path, _ = _license_source_archive(tmp_path, **{path: content})
    output = tmp_path / "package"
    with pytest.raises(ValueError, match="license"):
        extract_runtime_source(archive_path, output)
    assert not output.exists()


def test_portable_removes_vendor_caches_without_removing_sources_or_licenses(tmp_path):
    dependencies = tmp_path / "runtime/site-packages"
    cache = dependencies / "vendor/__pycache__"
    cache.mkdir(parents=True)
    source = dependencies / "vendor/__init__.py"
    source.write_text("# public vendor module\n")
    license_file = dependencies / "vendor/LICENSE.txt"
    license_file.write_text("public license\n")
    (cache / "__init__.cpython-310.pyc").write_bytes(b"unused wheel bytecode")
    remove_vendor_bytecode(dependencies, tmp_path)
    assert source.is_file() and license_file.is_file()
    assert not cache.exists()


def test_portable_cleanup_rejects_directories_outside_package(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(AssertionError):
        remove_vendor_bytecode(outside, tmp_path / "package")


@pytest.mark.skipif(os.name != "nt", reason="Windows long path regression")
def test_long_dependency_paths_remain_visible_and_vendor_caches_are_removed(tmp_path):
    package = filesystem_path(tmp_path / "package")
    dependencies = package / "runtime/site-packages"
    vendor = dependencies.joinpath(*(["long_dependency_path_" * 3] * 4))
    cache = vendor / "__pycache__"
    cache.mkdir(parents=True)
    source = vendor / "module.py"
    source.write_text("# long-path source\n", encoding="utf-8")
    bytecode = cache / "module.cpython-310.pyc"
    bytecode.write_bytes(b"old vendor bytecode")
    assert len(str(source)) > 260
    assert source in list(package.rglob("*.py"))
    remove_vendor_bytecode(dependencies, package)
    assert source.read_text(encoding="utf-8") == "# long-path source\n"
    assert not cache.exists()
