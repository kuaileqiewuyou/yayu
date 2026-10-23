from core.runtime.terminal_executor import execute_terminal_command
from llm.tools.tool_manager import ToolExecutionResult


TERMINAL_TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "command": {"type": "string", "description": "Shell command to execute."},
        "timeout": {"type": "integer", "description": "Optional timeout in seconds."},
        "workdir": {"type": "string", "description": "Optional working directory."},
        "background": {"type": "boolean", "description": "Run command in the background."},
        "notify_on_complete": {"type": "boolean", "description": "Request a one-shot completion notification for a background task."},
        "watch_patterns": {"type": "array", "items": {"type": "string"}, "description": "Optional substrings that emit a one-shot mid-run notification when matched in background task output."},
        "pty": {"type": "boolean", "description": "Run the command in PTY / interactive-terminal mode when supported."},
    },
    "required": ["command"],
}


TERMINAL_TOOL_DESCRIPTION = (
    "Execute a shell command on this computer. Use it to inspect, search, read, create, "
    "and write local files when the user asks, as well as to run programs and tests. "
    "Start long-running commands in background and use the process tool to control them. "
    "In managed mode every command requires one-time human approval because the shell is "
    "not confined to its working directory."
)


def register_terminal_tool(tool_manager, *, allowed_roots=None):
    def terminal(*, command, timeout=None, workdir=None, background=False, notify_on_complete=False, watch_patterns=None, pty=False):
        result = execute_terminal_command(
            command=command,
            timeout=timeout,
            workdir=workdir,
            background=background,
            notify_on_complete=notify_on_complete,
            watch_patterns=watch_patterns,
            pty=pty,
            allowed_roots=allowed_roots,
        )
        if isinstance(result, dict) and result.get("success") is False:
            return ToolExecutionResult(success=False, value=result, error=result.get("error"))
        return result

    tool_manager.register(
        "terminal",
        terminal,
        description=TERMINAL_TOOL_DESCRIPTION,
        parameters=TERMINAL_TOOL_PARAMETERS,
    )
