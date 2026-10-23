import os
from pathlib import Path
import subprocess
import sys


def test_real_qt_memory_chat_and_editor_round_trip(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        env.pop(key, None)
    result = subprocess.run([sys.executable, str(root / "scripts/smoke_memory.py"), str(tmp_path / "memory.png")],
                            cwd=root, env=env, capture_output=True, text=True, encoding="utf-8", timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: Qt send" in result.stdout
