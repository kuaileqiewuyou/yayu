"""Use a clean interpreter because older worker tests install synthetic Qt modules."""
import os
from pathlib import Path
import subprocess
import sys


def test_real_qt_streaming_and_cancellation():
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "smoke_streaming_cancel.py")],
        cwd=root, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: real Qt" in result.stdout
