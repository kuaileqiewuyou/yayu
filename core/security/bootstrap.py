from __future__ import annotations

import os
from pathlib import Path

from core.security.allowed_roots import AllowedRootsStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Keep the original storage key so renaming Yayu preserves explicit permissions.
SECURITY_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "galgame-agent" / "security"
_ALLOWED_ROOTS_STORE = AllowedRootsStore(
    SECURITY_ROOT / "allowed-roots.json",
    project_root=PROJECT_ROOT,
)


def get_allowed_roots_store() -> AllowedRootsStore:
    return _ALLOWED_ROOTS_STORE


def load_allowed_roots() -> list[Path]:
    return _ALLOWED_ROOTS_STORE.load()
