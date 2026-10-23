import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = PROJECT_ROOT / "scripts" / "start_gpt_sovits_api.ps1"


def test_gpt_sovits_launcher_is_generic_and_has_no_machine_path():
    source = LAUNCHER.read_text(encoding="utf-8")

    assert "gpt_sovits_api.local.yaml" in source
    assert "it never changes the loaded model" in source
    assert "will use the model already loaded by this API" in source
    assert "Noelle" not in source
    assert not re.search(r"[A-Za-z]:\\\\", source)


def test_gpt_sovits_local_runtime_config_is_ignored():
    patterns = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "data/config/gpt_sovits_*.local.yaml" in patterns
