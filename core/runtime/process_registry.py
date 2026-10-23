from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, UTC
from itertools import count
from threading import Lock, Thread
from typing import Any
import hashlib
import json
import subprocess

from core.security.audit_log import SecurityAuditLog, redact_security_text
from core.security.bootstrap import SECURITY_ROOT


@dataclass(frozen=True)
class PtyHostController:
    kind: str

    def apply_lifecycle(self, session: "ProcessSession", operation: str) -> None:
        if self.kind == "runner":
            if operation == "kill":
                session.host_state = "killed"
                session.status = "killed"
                session.ended_at = session.ended_at or datetime.now(UTC).isoformat()
                return
            if session.process is None:
                session.status = "blocked"
                return
            return_code = session.process.poll()
            if return_code is None:
                session.host_state = "running"
                session.status = "running"
                return
            session.exit_code = return_code
            session.ended_at = session.ended_at or datetime.now(UTC).isoformat()
            session.host_state = "exited" if return_code == 0 else "failed"
            session.status = "exited" if return_code == 0 else "failed"
            return
        if operation == "kill":
            session.host_state = "killed"
            session.status = "killed"
            session.ended_at = session.ended_at or datetime.now(UTC).isoformat()
            return
        if session.host_state == "killed":
            session.status = "killed"
            session.ended_at = session.ended_at or datetime.now(UTC).isoformat()
            return
        session.status = "blocked"


@dataclass
class ProcessSession:
    session_id: str
    process: subprocess.Popen | None
    started_at: str
    status: str = "running"
    stdout_lines: deque[str] | None = None
    stderr_lines: deque[str] | None = None
    ended_at: str | None = None
    exit_code: int | None = None
    stdin_available: bool = False
    stdin_closed: bool = False
    notify_on_complete: bool = False
    notification_emitted: bool = False
    watch_patterns: tuple[str, ...] = ()
    matched_watch_patterns: set[str] | None = None
    pty: bool = False
    session_type: str = "pipe_process"
    routing: str = "pipe_process"
    ordinary_pipe_process: bool = True
    host_kind: str | None = None
    host_state: str | None = None
    host_error: str | None = None
    host_controller: PtyHostController | None = None
    buffered_stdout: str = ""
    buffered_stderr: str = ""

    def __post_init__(self):
        if self.stdout_lines is None:
            self.stdout_lines = deque(maxlen=200)
        if self.stderr_lines is None:
            self.stderr_lines = deque(maxlen=200)
        if self.matched_watch_patterns is None:
            self.matched_watch_patterns = set()


class ProcessRegistry:
    def __init__(
        self,
        *,
        max_running_sessions: int = 8,
        audit_log: SecurityAuditLog | None = None,
    ):
        self._lock = Lock()
        self._sessions: dict[str, ProcessSession] = {}
        self._counter = count(1)
        self._notifications: list[dict[str, object]] = []
        self._pending_decisions: list[dict[str, object]] = []
        self._follow_up_events: list[dict[str, object]] = []
        self._max_running_sessions = max_running_sessions
        self._reserved_running_slots = 0
        self._audit_log = audit_log or SecurityAuditLog(SECURITY_ROOT / "audit.jsonl")

    def reserve_running_slot(self) -> None:
        with self._lock:
            running = sum(
                1 for current in self._sessions.values()
                if current.process is not None and current.process.poll() is None
            )
            if running + self._reserved_running_slots >= self._max_running_sessions:
                raise RuntimeError(
                    f"Maximum concurrent process sessions reached: {self._max_running_sessions}"
                )
            self._reserved_running_slots += 1

    def release_running_slot(self) -> None:
        with self._lock:
            if self._reserved_running_slots <= 0:
                raise RuntimeError("No reserved process session slot to release")
            self._reserved_running_slots -= 1

    def _register_running_session(self, session: ProcessSession, *, reserved: bool = False) -> None:
        """Atomically enforce the running-session limit and register a session."""
        with self._lock:
            running = sum(
                1 for current in self._sessions.values()
                if current.process is not None and current.process.poll() is None
            )
            if reserved:
                if self._reserved_running_slots <= 0:
                    raise RuntimeError("No reserved process session slot to consume")
                self._reserved_running_slots -= 1
            elif running + self._reserved_running_slots >= self._max_running_sessions:
                raise RuntimeError(
                    f"Maximum concurrent process sessions reached: {self._max_running_sessions}"
                )
            self._sessions[session.session_id] = session

    def start(self, process: subprocess.Popen, *, pty: bool = False, notify_on_complete: bool = False, watch_patterns: tuple[str, ...] = (), reserved: bool = False) -> dict[str, object]:
        session_id = f"proc-{next(self._counter)}"
        session = ProcessSession(
            session_id=session_id,
            process=process,
            started_at=datetime.now(UTC).isoformat(),
            stdin_available=process.stdin is not None,
            notify_on_complete=notify_on_complete,
            watch_patterns=watch_patterns,
            pty=pty,
            session_type="pipe_process",
            routing="pipe_process",
            ordinary_pipe_process=True,
        )
        try:
            self._register_running_session(session, reserved=reserved)
        except RuntimeError:
            if process.poll() is None:
                process.kill()
            raise
        self._start_reader_threads(session)
        return self._session_snapshot(session)

    def start_placeholder_session(
        self,
        *,
        pty: bool,
        session_type: str,
        routing: str,
        status: str,
        error: str,
        host_kind: str = "placeholder",
        host_state: str = "unimplemented",
    ) -> dict[str, object]:
        session_id = f"proc-{next(self._counter)}"
        now = datetime.now(UTC).isoformat()
        session = ProcessSession(
            session_id=session_id,
            process=None,
            started_at=now,
            ended_at=now,
            status=status,
            stdin_available=False,
            stdin_closed=True,
            pty=pty,
            session_type=session_type,
            routing=routing,
            ordinary_pipe_process=False,
            host_kind=host_kind,
            host_state=host_state,
            host_error=error,
            host_controller=PtyHostController(kind=host_kind),
        )
        session.stderr_lines.append(error + "\n")
        with self._lock:
            self._sessions[session_id] = session
        return self._session_snapshot(session)

    def start_host_runner_session(
        self,
        process: subprocess.Popen,
        *,
        pty: bool,
        session_type: str = "pty_host",
        routing: str = "dedicated_host_runner",
        host_kind: str = "runner",
        host_state: str = "running",
        buffered_stdout: str = "",
        buffered_stderr: str = "",
        notify_on_complete: bool = False,
        watch_patterns: tuple[str, ...] = (),
        reserved: bool = False,
    ) -> dict[str, object]:
        session_id = f"proc-{next(self._counter)}"
        session = ProcessSession(
            session_id=session_id,
            process=process,
            started_at=datetime.now(UTC).isoformat(),
            stdin_available=process.stdin is not None,
            notify_on_complete=notify_on_complete,
            watch_patterns=watch_patterns,
            pty=pty,
            session_type=session_type,
            routing=routing,
            ordinary_pipe_process=False,
            host_kind=host_kind,
            host_state=host_state,
            host_controller=PtyHostController(kind=host_kind),
            buffered_stdout=buffered_stdout,
            buffered_stderr=buffered_stderr,
        )
        try:
            self._register_running_session(session, reserved=reserved)
        except RuntimeError:
            if process.poll() is None:
                process.kill()
            raise
        self._start_reader_threads(session)
        return self._session_snapshot(session)

    def list_sessions(self) -> list[dict[str, object]]:
        with self._lock:
            sessions = list(self._sessions.values())
        return [self._session_snapshot(session) for session in sessions]

    def poll(self, session_id: str) -> dict[str, object]:
        session = self._get_session(session_id)
        self._refresh_status(session)
        return self._session_snapshot(session)

    def log(self, session_id: str, limit: int = 50, offset: int | None = None) -> dict[str, object]:
        session = self._get_session(session_id)
        self._refresh_status(session)
        stdout_lines = list(session.stdout_lines)
        stderr_lines = list(session.stderr_lines)
        if offset is None:
            stdout_view = stdout_lines[-limit:]
            stderr_view = stderr_lines[-limit:]
        else:
            normalized_offset = max(0, offset)
            stdout_view = stdout_lines[normalized_offset: normalized_offset + limit]
            stderr_view = stderr_lines[normalized_offset: normalized_offset + limit]
        return {
            "session_id": session.session_id,
            "status": session.status,
            "stdout": "".join(stdout_view),
            "stderr": "".join(stderr_view),
            "exit_code": session.exit_code,
        }

    def wait(self, session_id: str, timeout: int | None = None) -> dict[str, object]:
        session = self._get_session(session_id)
        if session.host_controller is not None:
            if session.process is not None:
                try:
                    session.process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    self._refresh_status(session)
                    return self._session_snapshot(session)
                self._drain_remaining_output(session)
                session.exit_code = session.process.returncode
                session.ended_at = session.ended_at or datetime.now(UTC).isoformat()
                if session.process.returncode == 0:
                    session.host_state = "exited"
                    session.status = "exited"
                else:
                    session.host_state = "failed"
                    session.status = "failed"
                self._maybe_emit_completion_notification(session)
            else:
                self._refresh_status(session)
            pid = session.process.pid if session.process is not None else None
            return {
                "session_id": session.session_id,
                "status": session.status,
                "pid": pid,
                "started_at": session.started_at,
                "ended_at": session.ended_at,
                "exit_code": session.exit_code,
                "stdin_available": session.stdin_available,
                "stdin_closed": session.stdin_closed,
                "pty": session.pty,
                "session_type": session.session_type,
                "routing": session.routing,
                "ordinary_pipe_process": session.ordinary_pipe_process,
                "host_kind": session.host_kind,
                "host_state": session.host_state,
                "host_error": session.host_error,
                "host_controller_kind": session.host_controller.kind if session.host_controller is not None else None,
            }
        if session.process is None:
            self._refresh_status(session)
            return self._session_snapshot(session)
        try:
            session.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._refresh_status(session)
            return self._session_snapshot(session)
        self._drain_remaining_output(session)
        self._refresh_status(session)
        return self._session_snapshot(session)

    def kill(self, session_id: str) -> dict[str, object]:
        session = self._get_session(session_id)
        if session.host_controller is not None:
            session.host_controller.apply_lifecycle(session, "kill")
        elif session.process is not None and session.process.poll() is None:
            session.process.kill()
        self._refresh_status(session, killed=True)
        return self._session_snapshot(session)

    def write(self, session_id: str, data: str, append_newline: bool = False) -> dict[str, object]:
        session = self._get_session(session_id)
        if not session.stdin_available or session.process.stdin is None:
            raise RuntimeError(f"Process session does not support stdin: {session_id}")
        if session.stdin_closed:
            raise RuntimeError(f"Process session stdin is closed: {session_id}")
        payload = data + ("\n" if append_newline else "")
        try:
            session.process.stdin.write(payload)
            session.process.stdin.flush()
        except BrokenPipeError as exc:
            session.stdin_closed = True
            raise RuntimeError(f"Process session stdin is closed: {session_id}") from exc
        return self._session_snapshot(session)

    def close_stdin(self, session_id: str) -> dict[str, object]:
        session = self._get_session(session_id)
        if not session.stdin_available or session.process.stdin is None:
            raise RuntimeError(f"Process session does not support stdin: {session_id}")
        if session.stdin_closed:
            raise RuntimeError(f"Process session stdin is already closed: {session_id}")
        try:
            session.process.stdin.close()
        finally:
            session.stdin_closed = True
        return self._session_snapshot(session)

    def consume_notifications(self) -> list[dict[str, object]]:
        with self._lock:
            notifications = list(self._notifications)
            self._notifications.clear()
        return notifications

    def create_pending_decision(
        self,
        *,
        request: dict[str, object],
        risk_level: str,
        reason: str,
    ) -> str:
        decision_id = f"decision-{next(self._counter)}"
        canonical_request = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        record = {
            "id": decision_id,
            "command": request["command"],
            "request": dict(request),
            "request_sha256": hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            "risk_level": risk_level,
            "reason": reason,
            "status": "pending",
        }
        with self._lock:
            self._pending_decisions.append(record)
        self._audit_log.record(
            "approval_requested",
            decision_id=decision_id,
            command=request.get("command", ""),
            risk_level=risk_level,
            reason=reason,
            status="pending",
        )
        return decision_id

    def claim_pending_decision(self, decision_id: str) -> dict[str, object]:
        """Claim a decision for one trusted execution, before any command is run."""
        with self._lock:
            record = next((item for item in self._pending_decisions if item["id"] == decision_id), None)
            if record is None:
                raise KeyError(f"Unknown pending decision: {decision_id}")
            if record["status"] != "pending":
                raise RuntimeError(f"Pending decision is already resolved: {decision_id}")
            request = dict(record["request"])
            canonical_request = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            fingerprint = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
            if fingerprint != record["request_sha256"]:
                record["status"] = "invalid"
                self._audit_log.record(
                    "approval_invalidated",
                    decision_id=decision_id,
                    status="invalid",
                )
                raise RuntimeError(f"Pending decision request was modified: {decision_id}")
            record["status"] = "executing"
            self._audit_log.record(
                "approval_claimed",
                decision_id=decision_id,
                status="executing",
            )
            return request

    def finish_pending_decision(self, decision_id: str, *, succeeded: bool) -> None:
        with self._lock:
            record = next((item for item in self._pending_decisions if item["id"] == decision_id), None)
            if record is None:
                raise KeyError(f"Unknown pending decision: {decision_id}")
            if record["status"] != "executing":
                raise RuntimeError(f"Pending decision is not executing: {decision_id}")
            record["status"] = "consumed" if succeeded else "failed"
            self._audit_log.record(
                "approval_finished",
                decision_id=decision_id,
                status=record["status"],
            )

    def deny_pending_decision(self, decision_id: str) -> None:
        with self._lock:
            record = next((item for item in self._pending_decisions if item["id"] == decision_id), None)
            if record is None:
                raise KeyError(f"Unknown pending decision: {decision_id}")
            if record["status"] != "pending":
                raise RuntimeError(f"Pending decision is already resolved: {decision_id}")
            record["status"] = "denied"
            self._audit_log.record(
                "approval_denied",
                decision_id=decision_id,
                status="denied",
            )

    def list_pending(self) -> dict[str, list[dict[str, object]]]:
        with self._lock:
            return {
                "notifications": list(self._notifications),
                "decisions": [self._public_pending_decision(item) for item in self._pending_decisions],
            }

    @staticmethod
    def _public_pending_decision(record: dict[str, object]) -> dict[str, object]:
        command = str(redact_security_text(record.get("command", "")))
        return {
            "id": record["id"],
            "command": command,
            "risk_level": record["risk_level"],
            "reason": record["reason"],
            "status": record["status"],
        }

    def list_follow_up_events(self) -> dict[str, list[dict[str, object]]]:
        with self._lock:
            return {"events": list(self._follow_up_events)}

    def _get_session(self, session_id: str) -> ProcessSession:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Unknown process session: {session_id}")
        return session

    def _refresh_status(self, session: ProcessSession, killed: bool = False) -> None:
        if session.host_controller is not None:
            operation = "kill" if killed else "refresh"
            session.host_controller.apply_lifecycle(session, operation)
            self._maybe_emit_completion_notification(session)
            return
        if session.process is None:
            if killed:
                session.status = "killed"
                session.ended_at = session.ended_at or datetime.now(UTC).isoformat()
            return
        return_code = session.process.poll()
        if return_code is None:
            session.status = "running"
            return
        session.exit_code = return_code
        session.ended_at = session.ended_at or datetime.now(UTC).isoformat()
        if killed:
            session.status = "killed"
        elif return_code == 0:
            session.status = "exited"
        else:
            session.status = "failed"
        self._maybe_emit_completion_notification(session)

    def _maybe_emit_completion_notification(self, session: ProcessSession) -> None:
        if not session.notify_on_complete or session.notification_emitted:
            return
        if session.status not in {"exited", "failed", "killed"}:
            return
        summary = {
            "session_id": session.session_id,
            "event_type": "completion",
            "status": session.status,
            "exit_code": session.exit_code,
            "stdout": "".join(list(session.stdout_lines)[-20:]),
            "stderr": "".join(list(session.stderr_lines)[-20:]),
        }
        follow_up = {
            "session_id": session.session_id,
            "event_type": "completion_follow_up",
            "status": session.status,
            "exit_code": session.exit_code,
        }
        with self._lock:
            self._notifications.append(summary)
            self._follow_up_events.append(follow_up)
        session.notification_emitted = True

    def _maybe_emit_watch_notification(self, session: ProcessSession, stream_name: str, line: str) -> None:
        if not session.watch_patterns:
            return
        for pattern in session.watch_patterns:
            if pattern in session.matched_watch_patterns:
                continue
            if pattern not in line:
                continue
            payload = {
                "session_id": session.session_id,
                "event_type": "watch_pattern_matched",
                "pattern": pattern,
                "status": session.status,
                "stdout": line if stream_name == "stdout" else "",
                "stderr": line if stream_name == "stderr" else "",
            }
            with self._lock:
                self._notifications.append(payload)
            session.matched_watch_patterns.add(pattern)

    def _session_snapshot(self, session: ProcessSession) -> dict[str, object]:
        self._refresh_status(session)
        pid = session.process.pid if session.process is not None else None
        return {
            "session_id": session.session_id,
            "status": session.status,
            "pid": pid,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
            "exit_code": session.exit_code,
            "stdin_available": session.stdin_available,
            "stdin_closed": session.stdin_closed,
            "pty": session.pty,
            "session_type": session.session_type,
            "routing": session.routing,
            "ordinary_pipe_process": session.ordinary_pipe_process,
            "host_kind": session.host_kind,
            "host_state": session.host_state,
            "host_error": session.host_error,
            "host_controller_kind": session.host_controller.kind if session.host_controller is not None else None,
        }

    def _start_reader_threads(self, session: ProcessSession) -> None:
        def pump(stream, target_deque, stream_name: str):
            try:
                for line in iter(stream.readline, ""):
                    if not line:
                        break
                    target_deque.append(line)
                    self._maybe_emit_watch_notification(session, stream_name, line)
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        if session.process.stdout is not None:
            Thread(target=pump, args=(session.process.stdout, session.stdout_lines, "stdout"), daemon=True).start()
        if session.process.stderr is not None:
            Thread(target=pump, args=(session.process.stderr, session.stderr_lines, "stderr"), daemon=True).start()

    def _drain_remaining_output(self, session: ProcessSession) -> None:
        if session.process is None:
            return
        if not session.stdout_lines and session.buffered_stdout:
            session.stdout_lines.extend(session.buffered_stdout.splitlines(keepends=True))
        if not session.stderr_lines and session.buffered_stderr:
            session.stderr_lines.extend(session.buffered_stderr.splitlines(keepends=True))
        if session.process.stdout is not None and not session.process.stdout.closed:
            remaining_stdout = session.process.stdout.read()
            if remaining_stdout:
                session.stdout_lines.extend(remaining_stdout.splitlines(keepends=True))
        if session.process.stderr is not None and not session.process.stderr.closed:
            remaining_stderr = session.process.stderr.read()
            if remaining_stderr:
                session.stderr_lines.extend(remaining_stderr.splitlines(keepends=True))


_process_registry: ProcessRegistry | None = None


def get_process_registry() -> ProcessRegistry:
    global _process_registry
    if _process_registry is None:
        _process_registry = ProcessRegistry()
    return _process_registry
