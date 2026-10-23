from pathlib import Path

from llm.tools.file_tools import register_file_tools
from llm.tools.tool_manager import ToolManager


def _manager_for(root: Path) -> ToolManager:
    manager = ToolManager()
    register_file_tools(
        manager,
        allowed_roots=[root],
        recovery_root=root / ".file-history",
    )
    return manager


def test_register_file_tools_exposes_read_and_list_definitions(tmp_path: Path) -> None:
    manager = _manager_for(tmp_path)

    assert {"read_file", "list_directory"} <= set(manager.list_tools())
    definitions = {
        item["function"]["name"]: item["function"]
        for item in manager.get_tool_definitions()
    }
    assert definitions["read_file"]["parameters"]["required"] == ["path"]
    assert definitions["list_directory"]["parameters"]["required"] == ["path"]


def test_register_file_tools_exposes_search_write_patch_and_undo(tmp_path: Path) -> None:
    manager = _manager_for(tmp_path)

    assert {"search_files", "write_file", "patch_file", "undo_file_operation"} <= set(
        manager.list_tools()
    )


def test_read_file_returns_paginated_text_with_line_metadata(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("一\n二\n三\n四\n", encoding="utf-8")
    manager = _manager_for(tmp_path)

    result = manager.call_tool(
        "read_file",
        {"path": str(target), "offset": 2, "limit": 2},
    )

    assert result.success is True
    assert result.value == {
        "path": str(target.resolve()),
        "content": "二\n三",
        "offset": 2,
        "limit": 2,
        "returned_lines": 2,
        "total_lines": 4,
        "next_offset": 4,
        "truncated": True,
    }


def test_list_directory_returns_sorted_non_recursive_entries(tmp_path: Path) -> None:
    (tmp_path / "z-dir").mkdir()
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    manager = _manager_for(tmp_path)

    result = manager.call_tool("list_directory", {"path": str(tmp_path)})

    assert result.success is True
    assert result.value["path"] == str(tmp_path.resolve())
    assert result.value["entries"] == [
        {"name": "a.txt", "path": str((tmp_path / "a.txt").resolve()), "type": "file", "size": 5},
        {"name": "z-dir", "path": str((tmp_path / "z-dir").resolve()), "type": "directory", "size": None},
    ]
    assert result.value["truncated"] is False


def test_file_tools_reject_paths_outside_allowed_roots(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "private.txt"
    outside.write_text("secret", encoding="utf-8")
    manager = _manager_for(allowed)

    result = manager.call_tool("read_file", {"path": str(outside)})

    assert result.success is False
    assert "outside allowed directories" in (result.error or "").lower()


def test_read_file_rejects_invalid_pagination(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("hello", encoding="utf-8")
    manager = _manager_for(tmp_path)

    result = manager.call_tool("read_file", {"path": str(target), "offset": 0})

    assert result.success is False
    assert "offset" in (result.error or "").lower()


def test_search_files_returns_line_matches_and_respects_glob(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("alpha\nneedle here\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("needle ignored\n", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "c.txt").write_text("another needle\n", encoding="utf-8")
    manager = _manager_for(tmp_path)

    result = manager.call_tool(
        "search_files",
        {"path": str(tmp_path), "query": "needle", "file_glob": "*.txt"},
    )

    assert result.success is True
    assert [(item["path"], item["line"], item["text"]) for item in result.value["matches"]] == [
        (str((tmp_path / "a.txt").resolve()), 2, "needle here"),
        (str((nested / "c.txt").resolve()), 1, "another needle"),
    ]
    assert result.value["truncated"] is False


def test_write_file_creates_recovery_point_and_returns_diff(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("old\n", encoding="utf-8")
    manager = _manager_for(tmp_path)

    result = manager.call_tool("write_file", {"path": str(target), "content": "new\n"})

    assert result.success is True
    assert target.read_text(encoding="utf-8") == "new\n"
    assert result.value["operation_id"].startswith("file-op-")
    assert "-old" in result.value["diff"]
    assert "+new" in result.value["diff"]
    assert result.value["created"] is False

    undo = manager.call_tool(
        "undo_file_operation", {"operation_id": result.value["operation_id"]}
    )
    assert undo.success is True
    assert target.read_text(encoding="utf-8") == "old\n"


def test_write_and_undo_new_file(tmp_path: Path) -> None:
    target = tmp_path / "new.txt"
    manager = _manager_for(tmp_path)

    result = manager.call_tool("write_file", {"path": str(target), "content": "hello"})
    assert result.success is True
    assert result.value["created"] is True
    assert target.read_text(encoding="utf-8") == "hello"

    undo = manager.call_tool(
        "undo_file_operation", {"operation_id": result.value["operation_id"]}
    )
    assert undo.success is True
    assert target.exists() is False


def test_patch_file_replaces_one_unique_fragment_and_can_undo(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("before\ntarget\nafter\n", encoding="utf-8")
    manager = _manager_for(tmp_path)

    result = manager.call_tool(
        "patch_file",
        {"path": str(target), "old_string": "target", "new_string": "changed"},
    )

    assert result.success is True
    assert target.read_text(encoding="utf-8") == "before\nchanged\nafter\n"
    manager.call_tool("undo_file_operation", {"operation_id": result.value["operation_id"]})
    assert target.read_text(encoding="utf-8") == "before\ntarget\nafter\n"


def test_patch_file_rejects_missing_or_ambiguous_fragment(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("same\nsame\n", encoding="utf-8")
    manager = _manager_for(tmp_path)

    missing = manager.call_tool(
        "patch_file",
        {"path": str(target), "old_string": "missing", "new_string": "new"},
    )
    ambiguous = manager.call_tool(
        "patch_file",
        {"path": str(target), "old_string": "same", "new_string": "new"},
    )

    assert missing.success is False
    assert "not found" in (missing.error or "").lower()
    assert ambiguous.success is False
    assert "more than once" in (ambiguous.error or "").lower()
    assert target.read_text(encoding="utf-8") == "same\nsame\n"


def test_undo_rejects_stale_file_state(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("old", encoding="utf-8")
    manager = _manager_for(tmp_path)
    result = manager.call_tool("write_file", {"path": str(target), "content": "new"})
    target.write_text("external", encoding="utf-8")

    undo = manager.call_tool(
        "undo_file_operation", {"operation_id": result.value["operation_id"]}
    )

    assert undo.success is False
    assert "changed since operation" in (undo.error or "").lower()
    assert target.read_text(encoding="utf-8") == "external"
