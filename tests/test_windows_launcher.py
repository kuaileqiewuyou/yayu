"""Build the real renamed GUI launchers and exercise their runtime selection."""
from __future__ import annotations

import os
import json
from pathlib import Path
import shutil
import subprocess
import time
import uuid

import pytest


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows .NET GUI launcher")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def compiled_launchers(tmp_path_factory):
    compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    if not compiler.is_file():
        compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework/v4.0.30319/csc.exe"
    if not compiler.is_file():
        pytest.skip(".NET Framework compiler is unavailable")
    output = tmp_path_factory.mktemp("yayu-launcher-build")
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(ROOT / "scripts/build_windows_launcher.ps1"), "-OutputDirectory", str(output)],
                   check=True, capture_output=True, timeout=30)
    stub = output / "runtime_probe.cs"
    stub.write_text('''using System;
using System.IO;
internal static class Probe {
    private static int Main(string[] args) {
        File.WriteAllLines(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "invocation.txt"),
            new [] {string.Join("|", args), Environment.CurrentDirectory,
                Environment.GetEnvironmentVariable("PYTHONHOME") ?? "",
                Environment.GetEnvironmentVariable("PYTHONPATH") ?? "",
                Environment.GetEnvironmentVariable("VIRTUAL_ENV") ?? ""});
        string wait = Environment.GetEnvironmentVariable("YAYU_PROBE_WAIT_FILE");
        while (!string.IsNullOrEmpty(wait) && !File.Exists(wait)) System.Threading.Thread.Sleep(25);
        string exit = Environment.GetEnvironmentVariable("YAYU_PROBE_EXIT_CODE");
        return string.IsNullOrEmpty(exit) ? 0 : int.Parse(exit);
    }
}
''', encoding="utf-8")
    probe = output / "probe.exe"
    subprocess.run([str(compiler), "/nologo", "/target:exe", "/out:" + str(probe), str(stub)],
                   check=True, capture_output=True, timeout=30)
    return output, probe


@pytest.mark.parametrize(("name", "portable", "expected"), [
    ("Yayu.exe", True, "-E|-u|portable_bootstrap.py"),
    ("Yayu Settings.exe", True, "-E|-u|portable_bootstrap.py|--settings"),
    ("Yayu.exe", False, "-E|-u|main.py"),
    ("Yayu Settings.exe", False, "-E|-u|webui_qt.py"),
])
def test_renamed_launcher_uses_adjacent_python_and_clears_foreign_environment(
        compiled_launchers, tmp_path, name, portable, expected):
    output, probe = compiled_launchers
    package = tmp_path / "芽语 portable folder"
    package.mkdir()
    launcher = package / name
    shutil.copyfile(output / name, launcher)
    for entry in ("main.py", "webui_qt.py", "portable_bootstrap.py"):
        (package / entry).write_text("# fixture entry\n", encoding="utf-8")
    python = package / ("runtime/python.exe" if portable else "venv/Scripts/python.exe")
    python.parent.mkdir(parents=True)
    shutil.copyfile(probe, python)
    environment = {**os.environ, "PYTHONHOME": "foreign-home", "PYTHONPATH": "foreign-path",
                   "VIRTUAL_ENV": "foreign-venv"}
    result = subprocess.run([str(launcher)], cwd=tmp_path, env=environment,
                            capture_output=True, timeout=15)
    assert result.returncode == 0
    assert (python.parent / "invocation.txt").read_text(encoding="utf-8-sig").splitlines() == [
        expected, str(package), "", "", ""]
    logs = list((package / "logs").glob("*.log"))
    assert len(logs) == 1
    assert "Exit code: 0" in logs[0].read_text(encoding="utf-8")


def test_both_launcher_file_properties_carry_the_new_brand(compiled_launchers):
    output, _ = compiled_launchers
    inspect = output / "inspect-properties.ps1"
    inspect.write_text('''param([string]$OutputDirectory)
$properties = foreach ($name in @('Yayu.exe', 'Yayu Settings.exe')) {
    $info = [System.Diagnostics.FileVersionInfo]::GetVersionInfo((Join-Path $OutputDirectory $name))
    [pscustomobject]@{name=$name; product=$info.ProductName; title=$info.FileDescription; description=$info.Comments}
}
$json = $properties | ConvertTo-Json -Compress
[System.IO.File]::WriteAllText((Join-Path $OutputDirectory 'version-info.json'), $json, [System.Text.Encoding]::UTF8)
''', encoding="utf-8")
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(inspect), "-OutputDirectory", str(output)],
                   check=True, capture_output=True, timeout=15)
    properties = json.loads((output / "version-info.json").read_text(encoding="utf-8-sig"))
    assert {item["name"] for item in properties} == {"Yayu.exe", "Yayu Settings.exe"}
    for item in properties:
        for field in ("product", "title", "description"):
            assert "芽语" in item[field] and "Yayu" in item[field]


def _portable_probe(compiled_launchers, package):
    output, probe = compiled_launchers
    package.mkdir()
    shutil.copyfile(output / "Yayu.exe", package / "Yayu.exe")
    (package / "runtime").mkdir()
    shutil.copyfile(probe, package / "runtime/python.exe")
    for name in ("main.py", "webui_qt.py", "portable_bootstrap.py"):
        (package / name).write_text("# fixture\n", encoding="utf-8")
    return package / "Yayu.exe"


def _wait_for(path, timeout=8):
    deadline = time.monotonic() + timeout
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(.025)
    assert path.exists(), f"Expected helper output: {path.name}"


def test_launcher_parent_holds_shared_installation_lock_until_child_exits(compiled_launchers, tmp_path):
    from core.updates.locking import update_lock

    package = tmp_path / "芽语 installed"
    executable = _portable_probe(compiled_launchers, package)
    exit_signal = tmp_path / "allow-runtime-exit"
    environment = {**os.environ, "YAYU_PROBE_WAIT_FILE": str(exit_signal)}
    process = subprocess.Popen([str(executable)], cwd=tmp_path, env=environment)
    try:
        _wait_for(package / "runtime/invocation.txt")
        assert process.poll() is None
        with pytest.raises(TimeoutError):
            with update_lock(package, timeout=0):
                pass
    finally:
        exit_signal.touch()
        process.wait(timeout=10)
    with update_lock(package, timeout=0):
        assert process.returncode == 0


def test_interrupted_update_recovery_runs_before_missing_runtime_checks(compiled_launchers, tmp_path):
    output, probe = compiled_launchers
    package = tmp_path / "待恢复 芽语"
    package.mkdir()
    executable = package / "Yayu.exe"
    shutil.copyfile(output / "Yayu.exe", executable)
    work = tmp_path / ".yayu-updates" / uuid.uuid4().hex
    python = work / "worker-runtime/python.exe"
    python.parent.mkdir(parents=True)
    shutil.copyfile(probe, python)
    script = work / "installer.py"
    script.write_text("# recovery fixture\n", encoding="utf-8")
    plan = work / "plan.json"
    plan.write_text("{}", encoding="utf-8")
    pending = {"token": uuid.uuid4().hex, "app_root": str(package), "plan_path": str(plan),
               "recovery_python": str(python), "recovery_script": str(script), "worker_pid": -1}
    (package / ".yayu-update-pending.json").write_text(json.dumps(pending), encoding="utf-8")
    result = subprocess.run([str(executable)], cwd=tmp_path, timeout=10)
    assert result.returncode == 0
    invocation = python.parent / "invocation.txt"
    _wait_for(invocation)
    arguments = invocation.read_text(encoding="utf-8-sig").splitlines()[0].split("|")
    assert arguments == ["-E", "-u", str(script), "--recover", str(plan)]


def test_failed_update_probation_does_not_block_rollback_with_launcher_dialog(compiled_launchers, tmp_path):
    package = tmp_path / "failed update"
    executable = _portable_probe(compiled_launchers, package)
    token = uuid.uuid4().hex
    (package / ".yayu-update-pending.json").write_text(
        json.dumps({"token": token, "app_root": str(package)}), encoding="utf-8")
    environment = {**os.environ, "YAYU_UPDATE_TOKEN": token, "YAYU_PROBE_EXIT_CODE": "7"}
    result = subprocess.run([str(executable)], cwd=tmp_path, env=environment, timeout=10)
    assert result.returncode == 7
