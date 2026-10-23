"""Pure helpers for named background images and legacy tag migration."""
from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath
import re
from typing import Any


_NUMBERED_TAG = re.compile(r"(?<!\S)(\d+)\s*[-:：]\s*")


def _value(item: Any, field: str, default: Any = "") -> Any:
    return item.get(field, default) if isinstance(item, Mapping) else getattr(item, field, default)


def _path_key(path: str) -> str:
    # Old settings may contain Windows separators even when opened on Linux.
    return path.strip().replace("\\", "/")


def _filename_label(path: str) -> str:
    return PurePosixPath(_path_key(path)).stem


def _legacy_labels(tags: str) -> dict[int, str]:
    matches = list(_NUMBERED_TAG.finditer(tags or ""))
    labels: dict[int, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(tags)
        label = tags[match.end():end].strip()
        number = int(match.group(1))
        if number > 0 and label:
            labels.setdefault(number, label)
    return labels


def entries_from_background(
    background: Any,
    kind: str = "scene",
) -> list[dict[str, str]]:
    """Return current files in runtime order, recovering their bound names.

    Structured names follow paths (including repeated occurrences), never row
    indices. Numbered legacy tags are only migration fallbacks for unbound files.
    Entries without a file in the current legacy list are deliberately omitted.
    """
    if kind != "scene":
        raise ValueError(f"Unknown background resource kind: {kind}")
    if background is None:
        return []

    paths = [_value(sprite, "path") for sprite in (_value(background, "sprites", []) or [])]
    bindings = _value(background, "scene_bindings", []) or []
    tags = _value(background, "bg_tags") or ""

    names_by_path: dict[str, deque[str]] = defaultdict(deque)
    for binding in bindings:
        path = str(_value(binding, "path") or "")
        if path.strip():
            names_by_path[_path_key(path)].append(str(_value(binding, "label") or "").strip())

    legacy = _legacy_labels(tags)
    entries = []
    for number, value in enumerate(paths, start=1):
        path = str(value or "")
        if not path.strip():
            continue
        bound_names = names_by_path.get(_path_key(path))
        label = bound_names.popleft() if bound_names else ""
        entries.append({
            "path": path,
            "label": label or legacy.get(number, "") or _filename_label(path),
        })
    return entries


def format_resource_tags(entries: Iterable[Any]) -> str:
    """Create the legacy numbered-name mirror for compatibility with old files."""
    labels = []
    for entry in entries:
        path = str(_value(entry, "path") or "")
        if not path.strip():
            continue
        label = str(_value(entry, "label") or "").strip() or _filename_label(path)
        labels.append(label)
    return "\n".join(f"{number}: {label}" for number, label in enumerate(labels, start=1))
