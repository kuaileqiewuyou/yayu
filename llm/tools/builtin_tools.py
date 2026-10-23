from llm.tools.file_tools import register_file_tools
from llm.tools.process_tool import register_process_tool
from llm.tools.terminal_tool import register_terminal_tool
from llm.tools.web_tools import register_configured_web_tools
from llm.tools.workspace_tool import register_workspace_info_tool


def register_builtin_tools(manager, *, allowed_roots=None) -> None:
    register_workspace_info_tool(manager, allowed_roots=allowed_roots)
    register_file_tools(manager, allowed_roots=allowed_roots)
    register_terminal_tool(manager, allowed_roots=allowed_roots)
    register_process_tool(manager)


__all__ = ["register_builtin_tools", "register_configured_web_tools", "register_workspace_info_tool"]
