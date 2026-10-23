import os
import json
from pathlib import Path
import subprocess
import sys


def test_real_settings_sprite_pack_actions(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    artifacts = tmp_path / "artifacts"
    result = subprocess.run(
        [sys.executable, str(root / "scripts/smoke_sprite_pack.py"), "--output-dir", str(artifacts)],
        cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "persisted bindings: PASS" in result.stdout
    report = json.loads((artifacts / "sprite-pack-report.json").read_text(encoding="utf-8"))
    assert report["qpa"] == "offscreen"
    assert report["isolated_config_paths"] == 6
    assert report["confirmations"] == ["cancel", "confirm"]
    assert report["default_confirmation"] == "cancel"
    assert report["remaining_sprite_ids"] == [8]
    assert report["save_failure_retains_sprite"] and report["retry_removes_unused_sprite"]
    assert report["persona_edit_preserved"] and not report["model_services_started"]
    for filename in ("sprite-pack-ui.png", "sprite-preview-ui.png"):
        assert (artifacts / filename).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert not (tmp_path / "data").exists()
