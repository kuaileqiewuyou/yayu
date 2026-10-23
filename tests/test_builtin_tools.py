from llm.tools.tool_manager import ToolManager
from llm.tools.builtin_tools import register_builtin_tools


def test_register_builtin_tools_adds_terminal_tool() -> None:
    manager = ToolManager()

    register_builtin_tools(manager)

    assert "terminal" in manager.list_tools()
    definitions = manager.get_tool_definitions()
    assert any(item["function"]["name"] == "terminal" for item in definitions)


def test_register_builtin_tools_adds_parameterless_workspace_info_tool() -> None:
    manager = ToolManager()

    register_builtin_tools(manager)

    assert "get_workspace_info" in manager.list_tools()
    result = manager.call_tool("get_workspace_info", {})
    assert result.success is True
    assert result.value["project_root"]
    assert result.value["process_cwd"]
    assert result.value["allowed_roots"]


def test_register_builtin_tools_adds_read_only_file_tools() -> None:
    manager = ToolManager()

    register_builtin_tools(manager)

    assert {
        "read_file",
        "list_directory",
        "search_files",
        "write_file",
        "patch_file",
        "undo_file_operation",
    } <= set(manager.list_tools())


def test_register_builtin_tools_shares_allowed_roots_with_terminal_and_file_tools(tmp_path) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    allowed_file = allowed / "inside.txt"
    allowed_file.write_text("inside", encoding="utf-8")
    manager = ToolManager()

    register_builtin_tools(manager, allowed_roots=[allowed])

    read_inside = manager.call_tool("read_file", {"path": str(allowed_file)})
    terminal_outside = manager.call_tool(
        "terminal",
        {"command": "printf outside", "workdir": str(outside), "timeout": 5},
    )
    assert read_inside.success is True
    assert terminal_outside.success is False
    assert terminal_outside.value["approval_required"] is True
    assert terminal_outside.value["allowed_roots"] == [str(allowed.resolve())]


def test_terminal_tool_explicitly_advertises_local_file_capability() -> None:
    manager = ToolManager()

    register_builtin_tools(manager)

    definition = next(
        item for item in manager.get_tool_definitions()
        if item["function"]["name"] == "terminal"
    )
    description = definition["function"]["description"].lower()
    assert "local files" in description
    assert "read" in description
    assert "write" in description
