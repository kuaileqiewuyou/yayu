from __future__ import annotations

from pathlib import Path
from typing import Any
import os
import re
import shutil
import subprocess

from core.runtime.process_registry import get_process_registry


DEFAULT_TERMINAL_TIMEOUT_SECONDS = 10
SENSITIVE_ENV_MARKERS = (
    "API_KEY",
    "ACCESS_TOKEN",
    "AUTH_TOKEN",
    "BEARER_TOKEN",
    "CLIENT_SECRET",
    "DATABASE_URL",
    "PASSWORD",
    "PRIVATE_KEY",
    "SECRET",
    "TOKEN",
)
SENSITIVE_PATH_PARTS = {
    ".aws",
    ".azure",
    ".gnupg",
    ".ssh",
    "credentials",
}


class TerminalExecutionError(RuntimeError):
    pass


class TerminalExecutionTimeout(TerminalExecutionError):
    pass


def _filtered_terminal_environment() -> dict[str, str]:
    return {
        name: value
        for name, value in os.environ.items()
        if not any(marker in name.upper() for marker in SENSITIVE_ENV_MARKERS)
    }


def _is_sensitive_workdir(workdir: object) -> bool:
    if not isinstance(workdir, str) or not workdir:
        return False
    parts = {part.casefold() for part in Path(workdir).expanduser().parts}
    return bool(parts & SENSITIVE_PATH_PARTS)


def _approval_required_result(
    *,
    command: str,
    request: dict[str, object],
    reason: str,
    allowed_roots: tuple[Path, ...] = (),
) -> dict[str, object]:
    decision_id = get_process_registry().create_pending_decision(
        request=request,
        risk_level="high",
        reason=reason,
    )
    return {
        "success": False,
        "approval_required": True,
        "risk_level": "high",
        "command": command,
        "workdir": request.get("workdir"),
        "background": request.get("background", False),
        "pty": request.get("pty", False),
        "allowed_roots": [str(root) for root in allowed_roots],
        "reason": reason,
        "pending_decision_id": decision_id,
        "error": "terminal command requires approval",
    }


def _assess_terminal_risk(
    command: str,
    request: dict[str, object],
    allowed_roots: tuple[Path, ...] = (),
) -> dict[str, object] | None:
    if _is_sensitive_workdir(request.get("workdir")):
        return _approval_required_result(
            command=command,
            request=request,
            reason="terminal workdir is inside a sensitive path and requires approval",
            allowed_roots=allowed_roots,
        )
    workdir = request.get("workdir")
    if allowed_roots and isinstance(workdir, str):
        resolved_workdir = Path(workdir).expanduser().resolve(strict=False)
        if not any(resolved_workdir == root or resolved_workdir.is_relative_to(root) for root in allowed_roots):
            return _approval_required_result(
                command=command,
                request=request,
                reason="terminal workdir is outside allowed roots and requires approval",
                allowed_roots=allowed_roots,
            )
    if allowed_roots:
        return _approval_required_result(
            command=command,
            request=request,
            reason=(
                "Terminal commands are not confined to their working directory; "
                "managed mode requires one-time human approval for every command"
            ),
            allowed_roots=allowed_roots,
        )
    normalized = command.strip().lower()
    high_risk_patterns = [
        "rm -rf",
        "shutdown",
        "reboot",
        "poweroff",
        "mkfs",
    ]
    if any(pattern in normalized for pattern in high_risk_patterns):
        return _approval_required_result(
            command=command,
            request=request,
            reason="command matches a destructive high-risk pattern and requires approval",
            allowed_roots=allowed_roots,
        )
    return None


def make_background_pty_placeholder_result(
    *,
    recognized_family: str | None = None,
    fallback_category: str = "unsupported_command_family",
    reason: str | None = None,
) -> dict[str, Any]:
    error = (
        "Background PTY sessions require a dedicated PTY host/session architecture; "
        "the current pipe-based background process model is not a valid PTY host, "
        "and only a placeholder PTY-host boundary result is implemented in this phase"
    )
    placeholder_session = get_process_registry().start_placeholder_session(
        pty=True,
        session_type="pty_host",
        routing="dedicated_host_required",
        status="blocked",
        error=error,
    )
    return {
        "success": False,
        "pty": True,
        "placeholder": True,
        "path": "pty_host",
        "session_type": "pty_host",
        "routing": "dedicated_host_required",
        "ordinary_pipe_process": False,
        "fallback_category": fallback_category,
        "recognized_family": recognized_family,
        "reason": reason or "pty command shape is not supported by the current capability model",
        **placeholder_session,
        "error": error,
    }


def _find_winpty() -> str | None:
    return shutil.which("winpty")


def _extract_supported_python_script_path(command: str) -> str | None:
    single_match = re.fullmatch(r"python\s+'([^']+\.py)'", command.strip())
    if single_match is not None:
        return single_match.group(1)
    double_match = re.fullmatch(r'python\s+"([^"]+\.py)"', command.strip())
    if double_match is not None:
        return double_match.group(1)
    return None


def _build_supported_python_script_argv(command: str) -> list[str] | None:
    script_path = _extract_supported_python_script_path(command)
    if script_path is None:
        return None
    return ["python", script_path]


def _resolve_pty_capability_class(command: str) -> tuple[str | None, list[str] | None]:
    resolvers = [
        ("python_script", _build_supported_python_script_argv),
        ("python_inline", _build_supported_python_dash_c_argv),
        ("python_unbuffered_inline", _build_supported_python_unbuffered_dash_c_argv),
        ("shell_lc_single_quoted", _build_supported_sh_dash_lc_argv),
        ("shell_lc_double_quoted", _build_supported_sh_dash_lc_double_quoted_argv),
        ("bash_lc_single_quoted", _build_supported_bash_dash_lc_single_quoted_argv),
        ("bash_lc_double_quoted", _build_supported_bash_dash_lc_double_quoted_argv),
    ]
    for class_name, resolver in resolvers:
        argv = resolver(command)
        if argv is not None:
            return class_name, argv
    return None, None


def _diagnose_unsupported_pty_shape(command: str) -> tuple[str, str]:
    normalized = command.strip()
    if normalized.startswith("python ") and '.py' in normalized and '"' in normalized:
        return (
            "unsupported_quoting_shape",
            "python script command was recognized conceptually, but this quoting shape is not supported by the current PTY capability model",
        )
    return (
        "unsupported_command_family",
        "pty command family is not supported by the current capability model",
    )


def _build_supported_python_dash_c_argv(command: str) -> list[str] | None:
    match = re.fullmatch(r'python\s+-c\s+"([^"]+)"', command.strip())
    if match is None:
        return None
    return ["python", "-c", match.group(1)]


def _build_supported_python_unbuffered_dash_c_argv(command: str) -> list[str] | None:
    match = re.fullmatch(r'python\s+-u\s+-c\s+"([^"]+)"', command.strip())
    if match is None:
        return None
    return ["python", "-u", "-c", match.group(1)]


def _build_supported_sh_dash_lc_argv(command: str) -> list[str] | None:
    match = re.fullmatch(r"sh\s+-lc\s+'([^']+)'", command.strip())
    if match is None:
        return None
    return ["sh", "-lc", match.group(1)]


def _build_supported_sh_dash_lc_double_quoted_argv(command: str) -> list[str] | None:
    match = re.fullmatch(r'sh\s+-lc\s+"([^"]+)"', command.strip())
    if match is None:
        return None
    return ["sh", "-lc", match.group(1)]


def _build_supported_bash_dash_lc_single_quoted_argv(command: str) -> list[str] | None:
    match = re.fullmatch(r"bash\s+-lc\s+'([^']+)'", command.strip())
    if match is None:
        return None
    return ["bash", "-lc", match.group(1)]


def _build_supported_bash_dash_lc_double_quoted_argv(command: str) -> list[str] | None:
    match = re.fullmatch(r'bash\s+-lc\s+"([^"]+)"', command.strip())
    if match is None:
        return None
    return ["bash", "-lc", match.group(1)]


def execute_terminal_command(
    *,
    command: str,
    timeout: int | None = None,
    workdir: str | None = None,
    background: bool = False,
    notify_on_complete: bool = False,
    watch_patterns: list[str] | tuple[str, ...] | None = None,
    pty: bool = False,
    allowed_roots: list[str | Path] | tuple[str | Path, ...] | None = None,
    _trusted_approval: bool = False,
) -> dict[str, object]:
    normalized_command = command.strip()
    if not normalized_command:
        raise TerminalExecutionError("terminal command must not be empty")

    request = {
        "command": command,
        "timeout": timeout,
        "workdir": workdir,
        "background": background,
        "notify_on_complete": notify_on_complete,
        "watch_patterns": list(watch_patterns or []),
        "pty": pty,
    }
    if not _trusted_approval:
        resolved_allowed_roots = tuple(
            Path(root).expanduser().resolve(strict=True) for root in (allowed_roots or [])
        )
        risk_result = _assess_terminal_risk(normalized_command, request, resolved_allowed_roots)
        if risk_result is not None:
            return risk_result

    cwd = None
    if workdir:
        candidate = Path(workdir)
        if not candidate.exists() or not candidate.is_dir():
            raise TerminalExecutionError(f"terminal workdir is invalid: {workdir}")
        cwd = str(candidate)

    effective_timeout = timeout if timeout is not None else DEFAULT_TERMINAL_TIMEOUT_SECONDS
    if effective_timeout <= 0:
        raise TerminalExecutionError("terminal timeout must be greater than zero")

    winpty_path = _find_winpty() if pty else None
    if pty and not winpty_path:
        raise TerminalExecutionError("PTY mode requires winpty, but winpty was not found in the current terminal backend")

    try:
        if background:
            registry = get_process_registry()
            registry.reserve_running_slot()
            normalized_watch_patterns = tuple(pattern for pattern in (watch_patterns or []) if pattern)
            process_command = command
            process_pty = False
            if pty:
                capability_class, supported_argv = _resolve_pty_capability_class(normalized_command)
                if supported_argv is None:
                    registry.release_running_slot()
                    fallback_category, fallback_reason = _diagnose_unsupported_pty_shape(normalized_command)
                    return make_background_pty_placeholder_result(
                        recognized_family=capability_class,
                        fallback_category=fallback_category,
                        reason=fallback_reason,
                    )
                try:
                    process = subprocess.Popen(
                        supported_argv,
                        cwd=cwd,
                        env=_filtered_terminal_environment(),
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        shell=False,
                    )
                except Exception:
                    registry.release_running_slot()
                    raise
                buffered_stdout = ""
                buffered_stderr = ""
                poll_result = process.poll()
                if poll_result is not None:
                    buffered_stdout, buffered_stderr = process.communicate()
                result = registry.start_host_runner_session(
                    process,
                    pty=True,
                    buffered_stdout=buffered_stdout,
                    buffered_stderr=buffered_stderr,
                    notify_on_complete=notify_on_complete,
                    watch_patterns=normalized_watch_patterns,
                    reserved=True,
                )
                result["pty_capability_class"] = capability_class
                return result
            try:
                process = subprocess.Popen(
                    process_command,
                    cwd=cwd,
                    env=_filtered_terminal_environment(),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    shell=True,
                )
            except Exception:
                registry.release_running_slot()
                raise
            return registry.start(
                process,
                pty=process_pty,
                notify_on_complete=notify_on_complete,
                watch_patterns=normalized_watch_patterns,
                reserved=True,
            )

        pty_command = normalized_command
        if winpty_path:
            pty_command = f'"{winpty_path}" {normalized_command}'

        completed = subprocess.run(
            pty_command,
            cwd=cwd,
            env=_filtered_terminal_environment(),
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            check=False,
            shell=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise TerminalExecutionTimeout(f"terminal command timeout after {effective_timeout} seconds") from exc
    except OSError as exc:
        raise TerminalExecutionError(f"terminal command could not be started: {exc}") from exc

    return {
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "exit_code": completed.returncode,
        "timed_out": False,
    }


def approve_terminal_decision(decision_id: str) -> dict[str, object]:
    """Trusted UI/controller boundary: execute exactly one stored request once."""
    registry = get_process_registry()
    request = registry.claim_pending_decision(decision_id)
    try:
        result = execute_terminal_command(**request, _trusted_approval=True)
    except Exception:
        registry.finish_pending_decision(decision_id, succeeded=False)
        raise
    registry.finish_pending_decision(decision_id, succeeded=True)
    return {
        "decision_id": decision_id,
        "status": "consumed",
        "result": result,
    }


def deny_terminal_decision(decision_id: str) -> dict[str, object]:
    """Trusted UI/controller boundary: permanently deny one stored request."""
    get_process_registry().deny_pending_decision(decision_id)
    return {"decision_id": decision_id, "status": "denied"}
