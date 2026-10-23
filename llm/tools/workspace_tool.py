from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_INFO_PARAMETERS = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}
WORKSPACE_INFO_DESCRIPTION = (
    "Return authoritative local workspace information without requiring a path. "
    "Use this when the user asks for the project root, workspace directory, current "
    "working directory, or directories the agent is allowed to access."
)


def register_workspace_info_tool(
    tool_manager,
    *,
    project_root: str | Path = DEFAULT_PROJECT_ROOT,
    allowed_roots: Iterable[str | Path] | None = None,
) -> None:
    resolved_project_root = Path(project_root).expanduser().resolve(strict=True)
    resolved_allowed_roots = [
        Path(root).expanduser().resolve(strict=True)
        for root in (allowed_roots or [resolved_project_root])
    ]

    def get_workspace_info():
        return {
            "project_root": str(resolved_project_root),
            "process_cwd": str(Path.cwd().resolve(strict=False)),
            "allowed_roots": [str(root) for root in resolved_allowed_roots],
        }

    tool_manager.register(
        "get_workspace_info",
        get_workspace_info,
        description=WORKSPACE_INFO_DESCRIPTION,
        parameters=WORKSPACE_INFO_PARAMETERS,
    )


__all__ = ["register_workspace_info_tool"]
