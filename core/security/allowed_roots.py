from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Callable, Iterable


class AllowedRootsStore:
    """Trusted persistence for user-approved local filesystem roots."""

    def __init__(self, path: str | Path, *, project_root: str | Path):
        self.path = Path(path).expanduser().resolve(strict=False)
        self.project_root = Path(project_root).expanduser().resolve(strict=True)
        self._lock = RLock()
        self._subscribers: list[Callable[[list[Path]], None]] = []

    def subscribe(self, callback: Callable[[list[Path]], None]) -> None:
        self._subscribers.append(callback)

    def load(self) -> list[Path]:
        with self._lock:
            raw_roots: list[object] = []
            if self.path.is_file():
                try:
                    payload = json.loads(self.path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    payload = {}
                if isinstance(payload, dict) and isinstance(payload.get("allowed_roots"), list):
                    raw_roots = payload["allowed_roots"]
            return self._normalize(raw_roots)

    def replace(self, roots: Iterable[str | Path]) -> list[Path]:
        normalized = self._normalize(list(roots))
        self._write(normalized)
        for callback in tuple(self._subscribers):
            callback(list(normalized))
        return normalized

    def add(self, root: str | Path) -> list[Path]:
        return self.replace([*self.load(), root])

    def remove(self, root: str | Path) -> list[Path]:
        target = Path(root).expanduser().resolve(strict=False)
        if target == self.project_root:
            raise PermissionError("The built-in project root cannot be removed")
        return self.replace(item for item in self.load() if item != target)

    def _normalize(self, roots: Iterable[object]) -> list[Path]:
        candidates = [self.project_root]
        for raw_root in roots:
            if not isinstance(raw_root, (str, Path)):
                continue
            try:
                root = Path(raw_root).expanduser().resolve(strict=True)
            except (OSError, RuntimeError):
                continue
            if root.is_dir():
                candidates.append(root)

        ordered: list[Path] = []
        for candidate in candidates:
            if candidate in ordered:
                continue
            if candidate != self.project_root and any(
                candidate == parent or candidate.is_relative_to(parent)
                for parent in ordered
            ):
                continue
            descendants = [
                root for root in ordered
                if root != self.project_root and root.is_relative_to(candidate)
            ]
            for descendant in descendants:
                ordered.remove(descendant)
            ordered.append(candidate)
        return ordered

    def _write(self, roots: list[Path]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"allowed_roots": [str(root) for root in roots if root != self.project_root]},
            ensure_ascii=False,
            indent=2,
        )
        fd, temporary_path = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=self.path.parent,
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
        except Exception:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
            raise
