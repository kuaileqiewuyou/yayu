from llm.tools.tool_manager import ToolManager

from llm.tools.terminal_tool import register_terminal_tool


def build_tool_manager(*, allowed_roots=None):
    manager = ToolManager()
    register_terminal_tool(manager, allowed_roots=allowed_roots)
    return manager


def test_terminal_tool_is_registered_as_builtin_tool():
    manager = build_tool_manager()

    assert "terminal" in manager.list_tools()


def test_terminal_tool_schema_is_exposed_to_model_requests():
    manager = build_tool_manager()

    definitions = manager.get_tool_definitions()
    definition = next(item for item in definitions if item["function"]["name"] == "terminal")

    assert definition["type"] == "function"
    assert "command" in definition["function"]["parameters"]["properties"]
    assert "timeout" in definition["function"]["parameters"]["properties"]
    assert "workdir" in definition["function"]["parameters"]["properties"]
    assert "pty" in definition["function"]["parameters"]["properties"]
    assert "notify_on_complete" in definition["function"]["parameters"]["properties"]
    assert "watch_patterns" in definition["function"]["parameters"]["properties"]


def test_terminal_tool_returns_structured_result_for_successful_command(tmp_path):
    manager = build_tool_manager()

    result = manager.call_tool(
        "terminal",
        {
            "command": "printf 'hello'",
            "workdir": str(tmp_path),
            "timeout": 5,
        },
    )

    assert result.success is True
    assert result.value["stdout"] == "hello"
    assert result.value["stderr"] == ""
    assert result.value["exit_code"] == 0
    assert result.value["timed_out"] is False


def test_terminal_tool_preserves_non_zero_exit_code_without_crashing(tmp_path):
    manager = build_tool_manager()

    result = manager.call_tool(
        "terminal",
        {
            "command": "sh -c 'echo boom >&2; exit 7'",
            "workdir": str(tmp_path),
            "timeout": 5,
        },
    )

    assert result.success is True
    assert result.value["stdout"] == ""
    assert "boom" in result.value["stderr"]
    assert result.value["exit_code"] == 7
    assert result.value["timed_out"] is False


def test_terminal_tool_rejects_empty_command():
    manager = build_tool_manager()

    result = manager.call_tool("terminal", {"command": "   "})

    assert result.success is False
    assert "empty" in result.error.lower()


def test_terminal_tool_allows_low_risk_command(tmp_path):
    manager = build_tool_manager()

    result = manager.call_tool(
        "terminal",
        {
            "command": "printf 'low-risk'",
            "workdir": str(tmp_path),
            "timeout": 5,
        },
    )

    assert result.success is True
    assert result.value["stdout"] == "low-risk"


def test_terminal_tool_blocks_high_risk_command_with_structured_approval_required_result(tmp_path):
    manager = build_tool_manager()

    result = manager.call_tool(
        "terminal",
        {
            "command": "rm -rf testdir",
            "workdir": str(tmp_path),
            "timeout": 5,
        },
    )

    assert result.success is False
    assert result.value is not None
    assert result.value["approval_required"] is True
    assert result.value["risk_level"] == "high"
    assert result.value["command"] == "rm -rf testdir"
    assert result.value["workdir"] == str(tmp_path)
    assert "approval" in result.error.lower()
    assert "fallback_category" not in result.value
    assert "pending_decision_id" in result.value


def test_terminal_tool_blocks_high_risk_background_command_before_spawn(tmp_path):
    manager = build_tool_manager()
    target = tmp_path / "must-survive.txt"
    target.write_text("safe", encoding="utf-8")

    result = manager.call_tool(
        "terminal",
        {
            "command": f'rm -rf "{target}"',
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
        },
    )

    assert result.success is False
    assert result.value["approval_required"] is True
    assert "session_id" not in result.value
    assert target.read_text(encoding="utf-8") == "safe"


def test_terminal_tool_requires_approval_for_sensitive_workdir(tmp_path):
    manager = build_tool_manager()
    sensitive_dir = tmp_path / ".ssh"
    sensitive_dir.mkdir()

    result = manager.call_tool(
        "terminal",
        {
            "command": "printf 'inspect'",
            "workdir": str(sensitive_dir),
            "timeout": 5,
        },
    )

    assert result.success is False
    assert result.value["approval_required"] is True
    assert result.value["risk_level"] == "high"
    assert result.value["workdir"] == str(sensitive_dir)
    assert "sensitive" in result.value["reason"].lower()


def test_terminal_tool_requires_approval_outside_allowed_roots(tmp_path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    manager = build_tool_manager(allowed_roots=[allowed])

    result = manager.call_tool(
        "terminal",
        {"command": "printf 'outside'", "workdir": str(outside), "timeout": 5},
    )

    assert result.success is False
    assert result.value["approval_required"] is True
    assert result.value["workdir"] == str(outside)
    assert result.value["allowed_roots"] == [str(allowed.resolve())]
    assert "outside allowed" in result.value["reason"].lower()


def test_terminal_tool_requires_approval_inside_allowed_root_because_shell_is_not_sandboxed(tmp_path):
    manager = build_tool_manager(allowed_roots=[tmp_path])

    result = manager.call_tool(
        "terminal",
        {"command": "printf 'inside'", "workdir": str(tmp_path), "timeout": 5},
    )

    assert result.success is False
    assert result.value["approval_required"] is True
    assert "not confined" in result.value["reason"].lower()
    assert "one-time human approval" in result.value["reason"].lower()


def test_terminal_tool_managed_mode_requires_approval_for_denylist_bypass_shapes(tmp_path):
    manager = build_tool_manager(allowed_roots=[tmp_path])

    for command in (
        "rm -fr target",
        "find . -delete",
        'python -c "import shutil; shutil.rmtree(\'target\')"',
        "rmdir /s /q target",
        "powershell Remove-Item -Recurse target",
    ):
        result = manager.call_tool(
            "terminal",
            {"command": command, "workdir": str(tmp_path), "timeout": 5},
        )
        assert result.success is False
        assert result.value["approval_required"] is True


def test_terminal_tool_does_not_leak_sensitive_parent_environment_variables(tmp_path, monkeypatch):
    manager = build_tool_manager()
    monkeypatch.setenv("GALGAME_AGENT_TEST_API_KEY", "super-secret-value")
    monkeypatch.setenv("GITHUB_TOKEN", "github-secret-value")
    monkeypatch.setenv("GH_TOKEN", "gh-secret-value")
    monkeypatch.setenv("HF_TOKEN", "hf-secret-value")
    monkeypatch.setenv("NPM_TOKEN", "npm-secret-value")
    monkeypatch.setenv("DATABASE_URL", "postgres://alice:database-secret@example.test/app")
    monkeypatch.setenv("GALGAME_AGENT_SAFE_VALUE", "visible-value")

    result = manager.call_tool(
        "terminal",
        {
            "command": (
                "sh -c 'printf \"%s|%s|%s|%s|%s|%s\" "
                "\"$GALGAME_AGENT_TEST_API_KEY\" \"$GITHUB_TOKEN\" \"$GH_TOKEN\" "
                "\"$HF_TOKEN\" \"$NPM_TOKEN\" \"$DATABASE_URL\"; "
                "printf \"|%s\" \"$GALGAME_AGENT_SAFE_VALUE\"'"
            ),
            "workdir": str(tmp_path),
            "timeout": 5,
        },
    )

    assert result.success is True
    assert result.value["stdout"] == "||||||visible-value"
    assert "super-secret-value" not in result.value["stdout"]


def test_terminal_tool_rejects_invalid_workdir():
    manager = build_tool_manager()

    result = manager.call_tool(
        "terminal",
        {
            "command": "printf 'hello'",
            "workdir": "Z:/path/that/does/not/exist",
            "timeout": 5,
        },
    )

    assert result.success is False
    assert "workdir" in result.error.lower()


def test_terminal_tool_reports_timeout_cleanly(tmp_path):
    manager = build_tool_manager()

    result = manager.call_tool(
        "terminal",
        {
            "command": "sleep 2",
            "workdir": str(tmp_path),
            "timeout": 1,
        },
    )

    assert result.success is False
    assert "timeout" in result.error.lower()


def test_terminal_tool_handles_explicit_pty_request(tmp_path):
    manager = build_tool_manager()

    result = manager.call_tool(
        "terminal",
        {
            "command": "printf 'hello'",
            "workdir": str(tmp_path),
            "timeout": 5,
            "pty": True,
        },
    )

    if result.success:
        assert "stdout" in result.value or "session_id" in result.value
    else:
        assert "winpty" in result.error.lower()


def test_terminal_tool_background_pty_request_is_explicitly_supported_or_rejected(tmp_path):
    manager = build_tool_manager()

    result = manager.call_tool(
        "terminal",
        {
            "command": "sleep 1",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )

    if result.success:
        assert result.value["pty"] is True
    else:
        assert "winpty" in result.error.lower() or "pty" in result.error.lower() or "unsupported" in result.error.lower()
