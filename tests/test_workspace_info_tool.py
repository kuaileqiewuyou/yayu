from pathlib import Path

from llm.tools.tool_manager import ToolManager
from llm.tools.workspace_tool import register_workspace_info_tool


def test_workspace_info_tool_returns_authoritative_paths_without_arguments(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    extra_root = tmp_path / "voices"
    process_cwd = tmp_path / "launch-directory"
    project_root.mkdir()
    extra_root.mkdir()
    process_cwd.mkdir()
    monkeypatch.chdir(process_cwd)
    manager = ToolManager()
    register_workspace_info_tool(
        manager,
        project_root=project_root,
        allowed_roots=[project_root, extra_root],
    )

    result = manager.call_tool("get_workspace_info", {})

    assert result.success is True
    assert result.value == {
        "project_root": str(project_root.resolve()),
        "process_cwd": str(process_cwd.resolve()),
        "allowed_roots": [str(project_root.resolve()), str(extra_root.resolve())],
    }


def test_workspace_info_tool_schema_requires_no_guessed_path(tmp_path):
    manager = ToolManager()
    register_workspace_info_tool(manager, project_root=tmp_path)

    definition = next(
        item["function"]
        for item in manager.get_tool_definitions()
        if item["function"]["name"] == "get_workspace_info"
    )

    assert definition["parameters"] == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    assert "project root" in definition["description"].lower()


def test_default_workspace_info_project_root_is_repository_root():
    manager = ToolManager()
    register_workspace_info_tool(manager)

    result = manager.call_tool("get_workspace_info", {})

    expected_root = Path(__file__).resolve().parents[1]
    assert result.success is True
    assert Path(result.value["project_root"]) == expected_root
    assert Path(result.value["allowed_roots"][0]) == expected_root
