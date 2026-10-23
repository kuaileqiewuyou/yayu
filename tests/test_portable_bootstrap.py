"""Portable startup must resolve and initialize data before importing the UI."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from types import SimpleNamespace
import weakref

import pytest

import portable_bootstrap


@pytest.fixture
def portable_root(tmp_path, monkeypatch):
    root = tmp_path / "unpacked app 中文"
    root.mkdir()
    external = tmp_path / "unrelated working directory"
    external.mkdir()
    monkeypatch.chdir(external)
    monkeypatch.setattr(portable_bootstrap, "__file__", str(root / "portable_bootstrap.py"))
    monkeypatch.setattr(sys, "argv", ["original.exe"])
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "existing user appdata"))
    monkeypatch.delenv("PYTHONDONTWRITEBYTECODE", raising=False)
    monkeypatch.delenv("YAYU_UPDATE_TOKEN", raising=False)
    monkeypatch.setenv("YAYU_PORTABLE_ROOT", "")
    return root


@pytest.mark.parametrize("arguments, entry_name", [
    ([], "main"),
    (["--settings"], "webui_qt"),
    (["-platform", "offscreen", "--settings"], "webui_qt"),
    (["--settings", "--settings", "-style", "Fusion"], "webui_qt"),
])
def test_environment_and_defaults_are_ready_before_entry_import(
    portable_root, monkeypatch, arguments, entry_name,
):
    root = portable_root
    events = []

    def initialize(config_dir, *, portable_resources):
        assert Path(config_dir) == root / "data" / "config"
        assert portable_resources is True
        events.append("initialize")

    def entry_main():
        events.append("entry")
        return 23

    def import_module(name):
        assert Path.cwd() == root
        assert Path(os.environ["LOCALAPPDATA"]) == root / "data" / "appdata"
        assert (root / "data" / "appdata").is_dir()
        assert os.environ["PYTHONDONTWRITEBYTECODE"] == "1"
        assert sys.dont_write_bytecode is True
        assert sys.argv == [str(root / f"{entry_name}.py"), *[
            argument for argument in arguments if argument != "--settings"
        ]]
        events.append(f"import:{name}")
        if name == "scripts.init_config":
            return SimpleNamespace(initialize=initialize)
        assert name == entry_name
        assert events[-2] == "initialize"
        return SimpleNamespace(main=entry_main)

    monkeypatch.setattr(portable_bootstrap.importlib, "import_module", import_module)

    assert portable_bootstrap.main(arguments) == 23
    assert events == ["import:scripts.init_config", "initialize", f"import:{entry_name}", "entry"]


def test_default_arguments_come_from_launcher_without_mutating_callers_list(portable_root, monkeypatch):
    launcher_arguments = ["launcher bootstrap.py", "--settings", "-platform", "offscreen"]
    monkeypatch.setattr(sys, "argv", launcher_arguments)
    monkeypatch.setattr(portable_bootstrap.importlib, "import_module", lambda name: (
        SimpleNamespace(initialize=lambda config_dir, *, portable_resources: [])
        if name == "scripts.init_config" else SimpleNamespace(main=lambda: None)
    ))

    assert portable_bootstrap.main() == 0
    assert launcher_arguments == ["launcher bootstrap.py", "--settings", "-platform", "offscreen"]
    assert sys.argv == [str(portable_root / "webui_qt.py"), "-platform", "offscreen"]


def test_initialization_failure_does_not_import_entry(portable_root, monkeypatch):
    imported = []

    def initialize(config_dir, *, portable_resources):
        assert portable_resources is True
        raise OSError("The extracted directory is read-only")

    def import_module(name):
        imported.append(name)
        return SimpleNamespace(initialize=initialize)

    monkeypatch.setattr(portable_bootstrap.importlib, "import_module", import_module)

    with pytest.raises(OSError, match="read-only"):
        portable_bootstrap.main([])
    assert imported == ["scripts.init_config"]


def test_native_plugin_directories_are_ready_before_import_and_handles_stay_alive(portable_root, monkeypatch):
    root = portable_root
    expected = [root / "runtime/Lib/site-packages" / name for name in ("PySide6", "shiboken6")]
    for directory in expected:
        directory.mkdir(parents=True)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(portable_bootstrap, "_DLL_DIRECTORY_HANDLES", {})
    references = []
    registrations = []

    class Handle:
        pass

    def add_directory(path):
        registrations.append(Path(path))
        handle = Handle()
        references.append(weakref.ref(handle))
        return handle

    def import_module(name):
        assert registrations == expected
        assert all(reference() is not None for reference in references)
        if name == "scripts.init_config":
            return SimpleNamespace(initialize=lambda config_dir, *, portable_resources: None)
        return SimpleNamespace(main=lambda: 0)

    monkeypatch.setattr(os, "add_dll_directory", add_directory, raising=False)
    monkeypatch.setattr(portable_bootstrap.importlib, "import_module", import_module)
    assert portable_bootstrap.main([]) == 0
    assert portable_bootstrap.main(["--settings"]) == 0
    assert registrations == expected
    assert all(reference() is not None for reference in references)


def test_real_initializer_preserves_existing_configs_and_only_fills_missing(portable_root, monkeypatch):
    # Exercise the real missing-only initializer against an extracted fixture;
    # no ConfigManager or local profile is instantiated.
    from scripts import init_config

    root = portable_root
    config_dir = root / "data" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "system_config.example.yaml").write_bytes(b"always_on_top: false\n")
    (config_dir / "background.example.yaml").write_bytes(b"[]\n")
    originals = {
        "api.yaml": b"llm_api_key: {}\n",
        "api.local.yaml": b"# user overlay fixture\nllm_model: {}\n",
        "characters.yaml": b"[]\n",
        "system_config.yaml": b"always_on_top: true\n",
    }
    for name, content in originals.items():
        (config_dir / name).write_bytes(content)
    monkeypatch.setattr(init_config, "_PROJECT_ROOT", root)
    imported = []

    def import_module(name):
        imported.append(name)
        if name == "scripts.init_config":
            return init_config
        assert (config_dir / "background.yaml").read_bytes() == b"[]\n"
        assert {name: (config_dir / name).read_bytes() for name in originals} == originals
        return SimpleNamespace(main=lambda: 0)

    monkeypatch.setattr(portable_bootstrap.importlib, "import_module", import_module)

    assert portable_bootstrap.main([]) == 0
    assert imported == ["scripts.init_config", "main"]
    before = {path.name: path.read_bytes() for path in config_dir.iterdir()}
    assert portable_bootstrap.main(["--settings"]) == 0
    assert {path.name: path.read_bytes() for path in config_dir.iterdir()} == before
