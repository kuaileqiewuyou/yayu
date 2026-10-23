from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock


def redact_security_text(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if re.search(
                    r"(?i)(?:api[_-]?key|access[_-]?token|auth[_-]?token|token|password|passwd|secret)",
                    str(key),
                )
                else redact_security_text(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_security_text(item) for item in value]
    if not isinstance(value, str):
        return value
    value = re.sub(
        r"(?i)(authorization\s*:\s*bearer\s+)[^\s'\"]+",
        r"\1[REDACTED]",
        value,
    )
    value = re.sub(
        r"(?i)(authorization\s*:\s*basic\s+)[^\s'\"]+",
        r"\1[REDACTED]",
        value,
    )
    value = re.sub(
        r'''(?ix)
        ((?:api[_-]?key|access[_-]?token|auth[_-]?token|token|password|passwd|secret)
        \s*[=:]\s*)
        (["']?)[^\s,"'};]+\2
        ''',
        r"\1[REDACTED]",
        value,
    )
    value = re.sub(
        r'''(?ix)
        (--(?:api[_-]?key|access[_-]?token|auth[_-]?token|token|password|secret)
        (?:\s+|=))
        (["']?)[^\s,"'};]+\2
        ''',
        r"\1[REDACTED]",
        value,
    )
    value = re.sub(
        r"(?i)((?:cookie|set-cookie)\s*:\s*)[^\r\n]+",
        r"\1[REDACTED]",
        value,
    )
    value = re.sub(
        r'''(?ix)
        ((?:api[_-]?key|access[_-]?token|auth[_-]?token|token|password|passwd|secret|
        aws[_-]?secret[_-]?access[_-]?key)
        \s+)
        (["']?)[^\s,"'};]+\2
        ''',
        r"\1[REDACTED]",
        value,
    )
    value = re.sub(
        r'''(?ix)
        (\s(?:-u|--user)(?:\s+|=))
        (["']?)[^\s,"'};]+\2
        ''',
        r"\1[REDACTED]",
        value,
    )
    value = re.sub(
        r"(?i)(https?://)[^\s/@:]+:[^\s/@]+@",
        r"\1[REDACTED]@",
        value,
    )
    return value


class SecurityAuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve(strict=False)
        self._lock = Lock()

    def record(self, event_type: str, **fields: object) -> None:
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            **{name: redact_security_text(value) for name, value in fields.items()},
        }
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
