from __future__ import annotations

import difflib
import hashlib
import json
import os
from collections.abc import Iterable
from datetime import UTC, datetime
from fnmatch import fnmatch
from itertools import count
from pathlib import Path
from threading import Lock

from config.atomic_io import atomic_write_text


DEFAULT_READ_LIMIT = 500
MAX_READ_LIMIT = 2000
DEFAULT_LIST_LIMIT = 200
MAX_LIST_LIMIT = 1000
DEFAULT_SEARCH_LIMIT = 100
MAX_SEARCH_LIMIT = 1000
MAX_DIFF_CHARS = 50_000

READ_FILE_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Text file path inside an allowed directory."},
        "offset": {"type": "integer", "description": "First line to return, starting at 1."},
        "limit": {"type": "integer", "description": "Maximum lines to return."},
    },
    "required": ["path"],
}
LIST_DIRECTORY_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Directory path inside an allowed directory."},
        "limit": {"type": "integer", "description": "Maximum entries to return."},
    },
    "required": ["path"],
}
SEARCH_FILES_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Directory to search recursively."},
        "query": {"type": "string", "description": "Literal text to find."},
        "file_glob": {"type": "string", "description": "Optional filename glob such as *.py."},
        "limit": {"type": "integer", "description": "Maximum matching lines to return."},
    },
    "required": ["path", "query"],
}
WRITE_FILE_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Text file to create or replace."},
        "content": {"type": "string", "description": "Complete UTF-8 text content."},
    },
    "required": ["path", "content"],
}
PATCH_FILE_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Existing UTF-8 text file to edit."},
        "old_string": {"type": "string", "description": "Unique exact text to replace."},
        "new_string": {"type": "string", "description": "Replacement text."},
    },
    "required": ["path", "old_string", "new_string"],
}
UNDO_FILE_OPERATION_PARAMETERS = {
    "type": "object",
    "properties": {
        "operation_id": {"type": "string", "description": "File operation id returned by write_file or patch_file."},
    },
    "required": ["operation_id"],
}


def _resolved_roots(allowed_roots: Iterable[str | Path]) -> tuple[Path, ...]:
    roots = tuple(Path(root).expanduser().resolve(strict=True) for root in allowed_roots)
    if not roots:
        raise ValueError("At least one allowed directory is required")
    if any(not root.is_dir() for root in roots):
        raise ValueError("Allowed roots must be directories")
    return roots


def _is_allowed(target: Path, roots: tuple[Path, ...]) -> bool:
    return any(target == root or target.is_relative_to(root) for root in roots)


def _resolve_existing_path(path: str, roots: tuple[Path, ...]) -> Path:
    target = Path(path).expanduser().resolve(strict=True)
    if not _is_allowed(target, roots):
        raise PermissionError(f"Path is outside allowed directories: {target}")
    return target


def _resolve_write_path(path: str, roots: tuple[Path, ...]) -> Path:
    candidate = Path(path).expanduser()
    target = candidate.resolve(strict=False)
    parent = target.parent.resolve(strict=True)
    if not _is_allowed(target, roots) or not _is_allowed(parent, roots):
        raise PermissionError(f"Path is outside allowed directories: {target}")
    if target.exists() and not target.is_file():
        raise ValueError(f"Path is not a file: {target}")
    return target


def _validate_range(name: str, value: int, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _unified_diff(path: Path, before: str, after: str) -> tuple[str, bool]:
    diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path.name}",
            tofile=f"b/{path.name}",
        )
    )
    truncated = len(diff) > MAX_DIFF_CHARS
    return diff[:MAX_DIFF_CHARS], truncated


class FileOperationStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self._lock = Lock()
        self._counter = count(1)

    def record(self, *, path: Path, before: str | None, after: str) -> str:
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            operation_id = f"file-op-{stamp}-{next(self._counter)}"
            operation_dir = self.root / operation_id
            operation_dir.mkdir()
            if before is not None:
                atomic_write_text(operation_dir / "before.txt", before)
            metadata = {
                "operation_id": operation_id,
                "path": str(path),
                "created": before is None,
                "before_hash": _text_hash(before) if before is not None else None,
                "after_hash": _text_hash(after),
                "created_at": datetime.now(UTC).isoformat(),
                "undone": False,
            }
            atomic_write_text(operation_dir / "metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
            return operation_id

    def undo(self, operation_id: str, roots: tuple[Path, ...]) -> dict[str, object]:
        if not operation_id.startswith("file-op-") or Path(operation_id).name != operation_id:
            raise ValueError("Invalid file operation id")
        operation_dir = self.root / operation_id
        metadata_path = operation_dir / "metadata.json"
        if not metadata_path.is_file():
            raise ValueError(f"Unknown file operation: {operation_id}")
        with self._lock:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("undone"):
                raise ValueError(f"File operation was already undone: {operation_id}")
            target = Path(metadata["path"]).resolve(strict=False)
            if not _is_allowed(target, roots):
                raise PermissionError(f"Path is outside allowed directories: {target}")
            if not target.is_file():
                raise RuntimeError(f"File changed since operation: {target}")
            current = target.read_text(encoding="utf-8")
            if _text_hash(current) != metadata["after_hash"]:
                raise RuntimeError(f"File changed since operation: {target}")
            if metadata["created"]:
                target.unlink()
            else:
                before = (operation_dir / "before.txt").read_text(encoding="utf-8")
                atomic_write_text(target, before)
            metadata["undone"] = True
            metadata["undone_at"] = datetime.now(UTC).isoformat()
            atomic_write_text(metadata_path, json.dumps(metadata, ensure_ascii=False, indent=2))
            return {"operation_id": operation_id, "path": str(target), "undone": True}


def register_file_tools(
    tool_manager,
    *,
    allowed_roots: Iterable[str | Path] | None = None,
    recovery_root: str | Path | None = None,
) -> None:
    roots = _resolved_roots(allowed_roots or [Path.cwd()])
    # Preserve the original storage key so existing undo records survive rebranding.
    default_recovery_root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "galgame-agent" / "file-history"
    operations = FileOperationStore(Path(recovery_root) if recovery_root else default_recovery_root)

    def read_file(*, path: str, offset: int = 1, limit: int = DEFAULT_READ_LIMIT):
        offset = _validate_range("offset", offset, minimum=1, maximum=2_147_483_647)
        limit = _validate_range("limit", limit, minimum=1, maximum=MAX_READ_LIMIT)
        target = _resolve_existing_path(path, roots)
        if not target.is_file():
            raise ValueError(f"Path is not a file: {target}")
        lines = target.read_text(encoding="utf-8").splitlines()
        selected = lines[offset - 1 : offset - 1 + limit]
        next_offset = offset + len(selected)
        truncated = next_offset <= len(lines)
        return {
            "path": str(target), "content": "\n".join(selected), "offset": offset,
            "limit": limit, "returned_lines": len(selected), "total_lines": len(lines),
            "next_offset": next_offset if truncated else None, "truncated": truncated,
        }

    def list_directory(*, path: str, limit: int = DEFAULT_LIST_LIMIT):
        limit = _validate_range("limit", limit, minimum=1, maximum=MAX_LIST_LIMIT)
        target = _resolve_existing_path(path, roots)
        if not target.is_dir():
            raise ValueError(f"Path is not a directory: {target}")
        children = sorted(target.iterdir(), key=lambda item: (item.name.casefold(), item.name))
        entries = []
        for child in children[:limit]:
            entry_type = "directory" if child.is_dir() else "file" if child.is_file() else "other"
            entries.append({
                "name": child.name, "path": str(child.resolve()), "type": entry_type,
                "size": child.stat().st_size if entry_type == "file" else None,
            })
        return {
            "path": str(target), "entries": entries, "returned_entries": len(entries),
            "total_entries": len(children), "truncated": len(entries) < len(children),
        }

    def search_files(*, path: str, query: str, file_glob: str = "*", limit: int = DEFAULT_SEARCH_LIMIT):
        if not query:
            raise ValueError("query must not be empty")
        limit = _validate_range("limit", limit, minimum=1, maximum=MAX_SEARCH_LIMIT)
        target = _resolve_existing_path(path, roots)
        if not target.is_dir():
            raise ValueError(f"Path is not a directory: {target}")
        matches = []
        truncated = False
        for candidate in sorted(target.rglob("*"), key=lambda item: str(item).casefold()):
            if not candidate.is_file() or not fnmatch(candidate.name, file_glob):
                continue
            resolved_candidate = candidate.resolve()
            if not _is_allowed(resolved_candidate, roots):
                continue
            try:
                lines = resolved_candidate.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for line_number, line in enumerate(lines, 1):
                if query not in line:
                    continue
                if len(matches) == limit:
                    truncated = True
                    break
                matches.append({"path": str(resolved_candidate), "line": line_number, "text": line})
            if truncated:
                break
        return {"path": str(target), "query": query, "matches": matches, "truncated": truncated}

    def apply_write(path: str, content: str) -> dict[str, object]:
        target = _resolve_write_path(path, roots)
        before = target.read_text(encoding="utf-8") if target.exists() else None
        if before == content:
            return {"path": str(target), "changed": False, "created": False, "operation_id": None, "diff": "", "diff_truncated": False}
        diff, diff_truncated = _unified_diff(target, before or "", content)
        operation_id = operations.record(path=target, before=before, after=content)
        try:
            atomic_write_text(target, content)
        except Exception:
            operation_dir = operations.root / operation_id
            for item in operation_dir.iterdir():
                item.unlink()
            operation_dir.rmdir()
            raise
        return {
            "path": str(target), "changed": True, "created": before is None,
            "operation_id": operation_id, "diff": diff, "diff_truncated": diff_truncated,
        }

    def write_file(*, path: str, content: str):
        return apply_write(path, content)

    def patch_file(*, path: str, old_string: str, new_string: str):
        if not old_string:
            raise ValueError("old_string must not be empty")
        target = _resolve_existing_path(path, roots)
        if not target.is_file():
            raise ValueError(f"Path is not a file: {target}")
        before = target.read_text(encoding="utf-8")
        occurrences = before.count(old_string)
        if occurrences == 0:
            raise ValueError("old_string was not found")
        if occurrences > 1:
            raise ValueError("old_string occurs more than once")
        return apply_write(str(target), before.replace(old_string, new_string, 1))

    def undo_file_operation(*, operation_id: str):
        return operations.undo(operation_id, roots)

    registrations = [
        ("read_file", read_file, "Read a UTF-8 text file from an allowed directory with line pagination.", READ_FILE_PARAMETERS),
        ("list_directory", list_directory, "List one directory non-recursively inside an allowed directory.", LIST_DIRECTORY_PARAMETERS),
        ("search_files", search_files, "Search UTF-8 text files recursively inside an allowed directory.", SEARCH_FILES_PARAMETERS),
        ("write_file", write_file, "Create or replace a UTF-8 text file with a recovery point and unified diff.", WRITE_FILE_PARAMETERS),
        ("patch_file", patch_file, "Replace one unique text fragment with a recovery point and unified diff.", PATCH_FILE_PARAMETERS),
        ("undo_file_operation", undo_file_operation, "Undo one file write if the file has not changed since that operation.", UNDO_FILE_OPERATION_PARAMETERS),
    ]
    for name, function, description, parameters in registrations:
        tool_manager.register(name, function, description=description, parameters=parameters)
