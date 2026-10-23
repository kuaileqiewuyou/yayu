from core.runtime.process_registry import get_process_registry


PROCESS_TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "description": "One of: list, poll, wait, log, kill, write, submit, close, notifications, pending, follow_up."},
        "session_id": {"type": "string", "description": "Background process session id or pending decision id, depending on action."},
        "timeout": {"type": "integer", "description": "Optional wait timeout in seconds."},
        "limit": {"type": "integer", "description": "Optional log line limit."},
        "offset": {"type": "integer", "description": "Optional log line offset for pagination."},
        "data": {"type": "string", "description": "Raw stdin text to write to the background process."},
    },
    "required": ["action"],
}


PROCESS_TOOL_DESCRIPTION = "Inspect and control background terminal processes, including minimal stdin interaction."


def register_process_tool(tool_manager):
    def process(*, action, session_id=None, timeout=None, limit=None, offset=None, data=None):
        registry = get_process_registry()
        try:
            if action == "list":
                return {"sessions": registry.list_sessions()}
            if action == "poll":
                return registry.poll(session_id)
            if action == "wait":
                return registry.wait(session_id, timeout=timeout)
            if action == "log":
                return registry.log(session_id, limit=limit or 50, offset=offset)
            if action == "kill":
                return registry.kill(session_id)
            if action == "write":
                return registry.write(session_id, data or "", append_newline=False)
            if action == "submit":
                return registry.write(session_id, data or "", append_newline=True)
            if action == "close":
                return registry.close_stdin(session_id)
            if action == "notifications":
                return {"notifications": registry.consume_notifications()}
            if action == "pending":
                return registry.list_pending()
            if action == "follow_up":
                return registry.list_follow_up_events()
            raise RuntimeError(f"Unsupported process action: {action}")
        except KeyError as exc:
            raise RuntimeError(str(exc)) from exc

    tool_manager.register(
        "process",
        process,
        description=PROCESS_TOOL_DESCRIPTION,
        parameters=PROCESS_TOOL_PARAMETERS,
    )
