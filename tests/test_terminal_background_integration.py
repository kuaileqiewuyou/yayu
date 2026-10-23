from core.runtime.tool_loop import run_serial_tool_loop
from llm.tools.tool_manager import ToolManager
from llm.tools.builtin_tools import register_builtin_tools


class FakeAdapter:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def generate(self, messages, *, tools=None, generation_config=None):
        self.calls.append(
            {
                "messages": [dict(message) for message in messages],
                "tools": tools,
                "generation_config": generation_config,
            }
        )
        return self._responses.pop(0)


def make_tool_call(tool_name, arguments, tool_call_id="call-1"):
    return {
        "id": tool_call_id,
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": arguments,
        },
    }


def make_assistant_response(content, tool_calls=None):
    response = {
        "role": "assistant",
        "content": content,
    }
    if tool_calls is not None:
        response["tool_calls"] = tool_calls
    return response


def build_tool_manager():
    manager = ToolManager()
    register_builtin_tools(manager)
    return manager


def test_terminal_tool_background_mode_returns_session_id_immediately(tmp_path):
    manager = build_tool_manager()

    result = manager.call_tool(
        "terminal",
        {
            "command": "sleep 1",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
        },
    )

    assert result.success is True
    assert "session_id" in result.value
    assert result.value["status"] == "running"


def test_terminal_tool_foreground_mode_still_preserves_phase6_contract(tmp_path):
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


def test_unified_tool_loop_can_start_background_terminal_task_and_reinject_handle(tmp_path):
    workdir = str(tmp_path).replace("\\", "\\\\")
    tool_arguments = (
        '{"command": "sleep 1", '
        f'"workdir": "{workdir}", '
        '"timeout": 5, '
        '"background": true}'
    )
    adapter = FakeAdapter(
        [
            make_assistant_response("", tool_calls=[make_tool_call("terminal", tool_arguments)]),
            make_assistant_response("Background task started."),
        ]
    )
    tool_manager = build_tool_manager()

    result = run_serial_tool_loop(
        messages=[{"role": "user", "content": "Start background task."}],
        adapter=adapter,
        tool_manager=tool_manager,
    )

    assert result.final_output == "Background task started."
    assert [record.tool_name for record in result.invocation_records] == ["terminal"]
    assert result.invocation_records[0].status == "success"
    assert len(adapter.calls) == 2


def test_unified_tool_loop_can_follow_up_with_process_poll_or_wait(tmp_path):
    tool_manager = build_tool_manager()
    start_result = tool_manager.call_tool(
        "terminal",
        {
            "command": "sleep 1",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
        },
    )
    assert start_result.success is True
    session_id = start_result.value["session_id"]

    process_arguments = '{"action": "poll", "session_id": "%s"}' % session_id
    adapter = FakeAdapter(
        [
            make_assistant_response("", tool_calls=[make_tool_call("process", process_arguments)]),
            make_assistant_response("Process status observed."),
        ]
    )

    result = run_serial_tool_loop(
        messages=[{"role": "user", "content": "Check process status."}],
        adapter=adapter,
        tool_manager=tool_manager,
    )

    assert result.final_output == "Process status observed."
    assert [record.tool_name for record in result.invocation_records] == ["process"]
    assert result.invocation_records[0].status == "success"
    assert len(adapter.calls) == 2


def test_background_terminal_session_defaults_to_non_pty(tmp_path):
    manager = build_tool_manager()

    result = manager.call_tool(
        "terminal",
        {
            "command": "sleep 1",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
        },
    )

    assert result.success is True
    assert result.value["pty"] is False


def test_background_terminal_pty_boundary_is_explicit(tmp_path):
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

    assert result.success is False
    assert result.value is not None
    assert result.value["session_type"] == "pty_host"
    assert result.value["routing"] == "dedicated_host_required"
    assert result.value["ordinary_pipe_process"] is False
    assert "session_id" in result.value
    assert result.value["pty"] is True
    assert result.value["status"] == "blocked"
    assert result.value["host_kind"] == "placeholder"
    assert result.value["host_state"] == "unimplemented"
    assert result.value["host_error"] == result.error
    assert result.value["host_controller_kind"] == "placeholder"
    assert "pty host" in result.error.lower() or "background pty" in result.error.lower()


def test_background_terminal_pty_supported_script_path_returns_real_host_runner_session(tmp_path):
    manager = build_tool_manager()
    script_path = tmp_path / "pty_supported_script.py"
    script_path.write_text("print('hello-from-real-host-runner')\n", encoding="utf-8")

    result = manager.call_tool(
        "terminal",
        {
            "command": f"python '{script_path}'",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )

    assert result.success is True
    assert result.value["pty"] is True
    assert result.value["session_type"] == "pty_host"
    assert result.value["ordinary_pipe_process"] is False
    assert result.value["host_kind"] == "runner"
    assert result.value["host_state"] == "running"
    assert result.value["host_controller_kind"] == "runner"


def test_background_terminal_pty_python_dash_c_command_returns_real_host_runner_session(tmp_path):
    manager = build_tool_manager()

    result = manager.call_tool(
        "terminal",
        {
            "command": 'python -c "print(\'hello-from-python-c-runner\')"',
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )

    assert result.success is True
    wait_result = manager.call_tool(
        "process",
        {
            "action": "wait",
            "session_id": result.value["session_id"],
            "timeout": 5,
        },
    )
    assert wait_result.success is True
    log_result = manager.call_tool(
        "process",
        {
            "action": "log",
            "session_id": result.value["session_id"],
            "limit": 20,
        },
    )
    assert log_result.success is True
    assert result.value["session_type"] == "pty_host"
    assert result.value["host_kind"] == "runner"
    assert "hello-from-python-c-runner" in log_result.value["stdout"]


def test_background_terminal_pty_sh_dash_lc_command_returns_real_host_runner_session(tmp_path):
    manager = build_tool_manager()

    result = manager.call_tool(
        "terminal",
        {
            "command": "sh -lc 'printf shell-family-runner'",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )

    assert result.success is True
    wait_result = manager.call_tool(
        "process",
        {
            "action": "wait",
            "session_id": result.value["session_id"],
            "timeout": 5,
        },
    )
    assert wait_result.success is True
    log_result = manager.call_tool(
        "process",
        {
            "action": "log",
            "session_id": result.value["session_id"],
            "limit": 20,
        },
    )
    assert log_result.success is True
    assert result.value["session_type"] == "pty_host"
    assert result.value["host_kind"] == "runner"
    assert "shell-family-runner" in log_result.value["stdout"]


def test_background_terminal_pty_python_unbuffered_dash_c_command_returns_real_host_runner_session(tmp_path):
    manager = build_tool_manager()

    result = manager.call_tool(
        "terminal",
        {
            "command": 'python -u -c "print(\'hello-from-python-u-c-runner\')"',
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )

    assert result.success is True
    wait_result = manager.call_tool(
        "process",
        {
            "action": "wait",
            "session_id": result.value["session_id"],
            "timeout": 5,
        },
    )
    assert wait_result.success is True
    log_result = manager.call_tool(
        "process",
        {
            "action": "log",
            "session_id": result.value["session_id"],
            "limit": 20,
        },
    )
    assert log_result.success is True
    assert result.value["session_type"] == "pty_host"
    assert result.value["host_kind"] == "runner"
    assert "hello-from-python-u-c-runner" in log_result.value["stdout"]


def test_supported_pty_command_families_map_to_capability_classes(tmp_path):
    manager = build_tool_manager()
    script_path = tmp_path / "pty_capability_script.py"
    script_path.write_text("print('capability-script')\n", encoding="utf-8")

    cases = [
        (f"python '{script_path}'", "python_script"),
        (f'python "{script_path}"', "python_script"),
        ('python -c "print(\'capability-inline\')"', "python_inline"),
        ('python -u -c "print(\'capability-unbuffered\')"', "python_unbuffered_inline"),
        ("sh -lc 'printf capability-shell'", "shell_lc_single_quoted"),
        ('sh -lc "printf capability-shell-double"', "shell_lc_double_quoted"),
        ("bash -lc 'printf capability-bash-single'", "bash_lc_single_quoted"),
        ('bash -lc "printf capability-bash-double"', "bash_lc_double_quoted"),
    ]

    for command, expected_class in cases:
        result = manager.call_tool(
            "terminal",
            {
                "command": command,
                "workdir": str(tmp_path),
                "timeout": 5,
                "background": True,
                "pty": True,
            },
        )
        assert result.success is True
        session_id = result.value["session_id"]
        try:
            assert result.value["pty_capability_class"] == expected_class
            # This checks command routing, so finish each case before starting
            # another instead of exhausting the shared background-session limit.
            waited = manager.call_tool(
                "process", {"action": "wait", "session_id": session_id, "timeout": 5}
            )
            assert waited.success is True
            assert waited.value["exit_code"] == 0
        finally:
            manager.call_tool("process", {"action": "kill", "session_id": session_id})


def test_double_quoted_python_script_maps_to_supported_capability_class(tmp_path):
    manager = build_tool_manager()
    script_path = tmp_path / "double_quoted_capability_script.py"
    script_path.write_text("print('double-quoted-script')\n", encoding="utf-8")

    result = manager.call_tool(
        "terminal",
        {
            "command": f'python "{script_path}"',
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )

    assert result.success is True
    assert result.value is not None
    assert result.value["pty_capability_class"] == "python_script"
    assert result.value["host_kind"] == "runner"
    assert result.value["host_controller_kind"] == "runner"


def test_unsupported_pty_command_family_returns_structured_fallback(tmp_path):
    manager = build_tool_manager()

    result = manager.call_tool(
        "terminal",
        {
            "command": "node -e \"console.log('x')\"",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )

    assert result.success is False
    assert result.value is not None
    assert result.value["fallback_category"] == "unsupported_command_family"
    assert result.value["recognized_family"] is None
    assert "family" in result.value["reason"].lower()


def test_unsupported_pty_quoting_shape_returns_specific_structured_fallback(tmp_path):
    manager = build_tool_manager()

    result = manager.call_tool(
        "terminal",
        {
            "command": 'python "quoted but missing .py suffix and unsupported quoting"',
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )

    assert result.success is False
    assert result.value is not None
    assert result.value["fallback_category"] == "unsupported_quoting_shape"
    assert "quoting shape" in result.value["reason"].lower()


def test_process_list_distinguishes_real_host_runner_from_placeholder_fallback(tmp_path):
    manager = build_tool_manager()
    script_path = tmp_path / "pty_supported_script.py"
    script_path.write_text("print('hello-from-real-host-runner')\n", encoding="utf-8")

    real_result = manager.call_tool(
        "terminal",
        {
            "command": f"python '{script_path}'",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )
    assert real_result.success is True

    placeholder_result = manager.call_tool(
        "terminal",
        {
            "command": "sleep 1",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )
    assert placeholder_result.success is False

    list_result = manager.call_tool("process", {"action": "list"})
    assert list_result.success is True

    real_session = next(
        session
        for session in list_result.value["sessions"]
        if session["session_id"] == real_result.value["session_id"]
    )
    placeholder_session = next(
        session
        for session in list_result.value["sessions"]
        if session["session_id"] == placeholder_result.value["session_id"]
    )

    assert real_session["host_kind"] == "runner"
    assert real_session["host_state"] == "running"
    assert real_session["host_controller_kind"] == "runner"
    assert placeholder_session["host_kind"] == "placeholder"
    assert placeholder_session["host_state"] == "unimplemented"
    assert placeholder_session["host_controller_kind"] == "placeholder"


def test_process_log_can_read_output_from_real_host_runner_session(tmp_path):
    manager = build_tool_manager()
    script_path = tmp_path / "pty_supported_output_script.py"
    script_path.write_text("print('hello-from-real-host-runner-log')\n", encoding="utf-8")

    start_result = manager.call_tool(
        "terminal",
        {
            "command": f"python '{script_path}'",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )

    assert start_result.success is True

    wait_result = manager.call_tool(
        "process",
        {
            "action": "wait",
            "session_id": start_result.value["session_id"],
            "timeout": 5,
        },
    )
    assert wait_result.success is True

    log_result = manager.call_tool(
        "process",
        {
            "action": "log",
            "session_id": start_result.value["session_id"],
            "limit": 20,
        },
    )

    assert log_result.success is True
    assert "hello-from-real-host-runner-log" in log_result.value["stdout"]
    assert log_result.value["stderr"] == ""


def test_real_host_runner_session_can_receive_submit_input(tmp_path):
    manager = build_tool_manager()
    script_path = tmp_path / "pty_submit_script.py"
    script_path.write_text("print(input())\n", encoding="utf-8")

    start_result = manager.call_tool(
        "terminal",
        {
            "command": f"python '{script_path}'",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )
    assert start_result.success is True

    submit_result = manager.call_tool(
        "process",
        {
            "action": "submit",
            "session_id": start_result.value["session_id"],
            "data": "hello from pty runner stdin",
        },
    )
    assert submit_result.success is True

    wait_result = manager.call_tool(
        "process",
        {
            "action": "wait",
            "session_id": start_result.value["session_id"],
            "timeout": 5,
        },
    )
    assert wait_result.success is True

    log_result = manager.call_tool(
        "process",
        {
            "action": "log",
            "session_id": start_result.value["session_id"],
            "limit": 20,
        },
    )
    assert log_result.success is True
    assert "hello from pty runner stdin" in log_result.value["stdout"]


def test_real_host_runner_session_can_receive_write_and_close_input(tmp_path):
    manager = build_tool_manager()
    script_path = tmp_path / "pty_write_close_script.py"
    script_path.write_text("import sys\nprint(sys.stdin.read().upper())\n", encoding="utf-8")

    start_result = manager.call_tool(
        "terminal",
        {
            "command": f"python '{script_path}'",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )
    assert start_result.success is True

    write_result = manager.call_tool(
        "process",
        {
            "action": "write",
            "session_id": start_result.value["session_id"],
            "data": "abc",
        },
    )
    assert write_result.success is True

    close_result = manager.call_tool(
        "process",
        {
            "action": "close",
            "session_id": start_result.value["session_id"],
        },
    )
    assert close_result.success is True

    wait_result = manager.call_tool(
        "process",
        {
            "action": "wait",
            "session_id": start_result.value["session_id"],
            "timeout": 5,
        },
    )
    assert wait_result.success is True

    log_result = manager.call_tool(
        "process",
        {
            "action": "log",
            "session_id": start_result.value["session_id"],
            "limit": 20,
        },
    )
    assert log_result.success is True
    assert "ABC" in log_result.value["stdout"]


def test_background_terminal_task_with_notify_on_complete_produces_completion_notification(tmp_path):
    manager = build_tool_manager()

    start_result = manager.call_tool(
        "terminal",
        {
            "command": "printf 'notify-done'",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "notify_on_complete": True,
        },
    )
    assert start_result.success is True

    wait_result = manager.call_tool(
        "process",
        {
            "action": "wait",
            "session_id": start_result.value["session_id"],
            "timeout": 5,
        },
    )
    assert wait_result.success is True

    notifications_result = manager.call_tool("process", {"action": "notifications"})
    assert notifications_result.success is True
    matching = [
        item for item in notifications_result.value["notifications"]
        if item["session_id"] == start_result.value["session_id"]
    ]
    assert len(matching) == 1
    assert matching[0]["status"] in {"exited", "failed", "killed"}


def test_process_log_supports_offset_pagination_for_long_output(tmp_path):
    manager = build_tool_manager()

    start_result = manager.call_tool(
        "terminal",
        {
            "command": "python -c \"print('line1'); print('line2'); print('line3'); print('line4')\"",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
        },
    )
    assert start_result.success is True

    wait_result = manager.call_tool(
        "process",
        {
            "action": "wait",
            "session_id": start_result.value["session_id"],
            "timeout": 5,
        },
    )
    assert wait_result.success is True

    first_page = manager.call_tool(
        "process",
        {
            "action": "log",
            "session_id": start_result.value["session_id"],
            "offset": 0,
            "limit": 2,
        },
    )
    second_page = manager.call_tool(
        "process",
        {
            "action": "log",
            "session_id": start_result.value["session_id"],
            "offset": 2,
            "limit": 2,
        },
    )

    assert first_page.success is True
    assert second_page.success is True
    assert first_page.value["stdout"] == "line1\nline2\n"
    assert second_page.value["stdout"] == "line3\nline4\n"


def test_background_pty_log_pagination_is_consistent_across_selected_capability_classes(tmp_path):
    manager = build_tool_manager()

    python_script = tmp_path / "pty_pagination_python_script.py"
    python_script.write_text(
        "print('py-line1')\nprint('py-line2')\nprint('py-line3')\nprint('py-line4')\n",
        encoding="utf-8",
    )
    scenarios = [
        (
            "python_script",
            f"python '{python_script}'",
            "py-line1\npy-line2\n",
            "py-line3\npy-line4\n",
        ),
        (
            "shell_lc_single_quoted",
            "sh -lc 'printf \"shell-line1\\nshell-line2\\nshell-line3\\nshell-line4\\n\"'",
            "shell-line1\nshell-line2\n",
            "shell-line3\nshell-line4\n",
        ),
    ]

    for capability_class, command, first_expected, second_expected in scenarios:
        start_result = manager.call_tool(
            "terminal",
            {
                "command": command,
                "workdir": str(tmp_path),
                "timeout": 5,
                "background": True,
                "pty": True,
            },
        )
        assert start_result.success is True
        assert start_result.value["pty_capability_class"] == capability_class

        wait_result = manager.call_tool(
            "process",
            {
                "action": "wait",
                "session_id": start_result.value["session_id"],
                "timeout": 5,
            },
        )
        assert wait_result.success is True

        first_page = manager.call_tool(
            "process",
            {
                "action": "log",
                "session_id": start_result.value["session_id"],
                "offset": 0,
                "limit": 2,
            },
        )
        second_page = manager.call_tool(
            "process",
            {
                "action": "log",
                "session_id": start_result.value["session_id"],
                "offset": 2,
                "limit": 2,
            },
        )

        assert first_page.success is True
        assert second_page.success is True
        assert first_page.value["status"] == "exited"
        assert second_page.value["status"] == "exited"
        assert first_page.value["stdout"] == first_expected
        assert second_page.value["stdout"] == second_expected
        assert first_page.value["stderr"] == ""
        assert second_page.value["stderr"] == ""


def test_real_host_runner_task_with_notify_on_complete_produces_completion_notification(tmp_path):
    manager = build_tool_manager()
    script_path = tmp_path / "pty_notify_script.py"
    script_path.write_text("print('pty-notify-done')\n", encoding="utf-8")

    start_result = manager.call_tool(
        "terminal",
        {
            "command": f"python '{script_path}'",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "notify_on_complete": True,
            "pty": True,
        },
    )
    assert start_result.success is True

    wait_result = manager.call_tool(
        "process",
        {
            "action": "wait",
            "session_id": start_result.value["session_id"],
            "timeout": 5,
        },
    )
    assert wait_result.success is True

    notifications_result = manager.call_tool("process", {"action": "notifications"})
    assert notifications_result.success is True
    matching = [
        item for item in notifications_result.value["notifications"]
        if item["session_id"] == start_result.value["session_id"]
    ]
    assert len(matching) == 1
    assert matching[0]["status"] in {"exited", "failed", "killed"}
    assert "pty-notify-done" in matching[0]["stdout"]


def test_background_pty_completion_notifications_are_consistent_across_selected_capability_classes(tmp_path):
    manager = build_tool_manager()

    python_script = tmp_path / "pty_notify_matrix_python_script.py"
    python_script.write_text("print('notify-python-script')\n", encoding="utf-8")
    scenarios = [
        (
            "python_script",
            f"python '{python_script}'",
            "notify-python-script",
        ),
        (
            "shell_lc_single_quoted",
            "sh -lc 'printf \"notify-shell-single\"'",
            "notify-shell-single",
        ),
    ]

    for capability_class, command, expected_output in scenarios:
        start_result = manager.call_tool(
            "terminal",
            {
                "command": command,
                "workdir": str(tmp_path),
                "timeout": 5,
                "background": True,
                "notify_on_complete": True,
                "pty": True,
            },
        )
        assert start_result.success is True
        assert start_result.value["pty_capability_class"] == capability_class

        wait_result = manager.call_tool(
            "process",
            {
                "action": "wait",
                "session_id": start_result.value["session_id"],
                "timeout": 5,
            },
        )
        assert wait_result.success is True

        notifications_result = manager.call_tool("process", {"action": "notifications"})
        assert notifications_result.success is True
        matching = [
            item for item in notifications_result.value["notifications"]
            if item["session_id"] == start_result.value["session_id"]
        ]

        assert len(matching) == 1
        assert matching[0]["event_type"] == "completion"
        assert matching[0]["status"] == "exited"
        assert matching[0]["exit_code"] == 0
        assert expected_output in matching[0]["stdout"]
        assert matching[0]["stderr"] == ""

        follow_up_result = manager.call_tool("process", {"action": "follow_up"})
        assert follow_up_result.success is True
        follow_up_matching = [
            item for item in follow_up_result.value["events"]
            if item.get("session_id") == start_result.value["session_id"]
        ]
        assert len(follow_up_matching) == 1
        assert follow_up_matching[0]["event_type"] == "completion_follow_up"
        assert follow_up_matching[0]["status"] == "exited"
        assert follow_up_matching[0]["exit_code"] == 0


def test_selected_capability_classes_share_expected_minimum_contract_matrix(tmp_path):
    manager = build_tool_manager()
    script_path = tmp_path / "matrix_script.py"
    script_path.write_text("print(input())\n", encoding="utf-8")

    output_cases = [
        (f"python '{script_path}'", "python_script"),
        (f'python "{script_path}"', "python_script"),
        ('python -c "print(\'matrix-inline\')"', "python_inline"),
        ('python -u -c "print(\'matrix-unbuffered\')"', "python_unbuffered_inline"),
        ("sh -lc 'printf matrix-shell-single'", "shell_lc_single_quoted"),
        ('sh -lc "printf matrix-shell-double"', "shell_lc_double_quoted"),
        ("bash -lc 'printf matrix-bash-single'", "bash_lc_single_quoted"),
        ('bash -lc "printf matrix-bash-double"', "bash_lc_double_quoted"),
    ]

    for command, expected_class in output_cases:
        start_result = manager.call_tool(
            "terminal",
            {
                "command": command,
                "workdir": str(tmp_path),
                "timeout": 5,
                "background": True,
                "pty": True,
                "notify_on_complete": True,
            },
        )
        assert start_result.success is True
        assert start_result.value["pty_capability_class"] == expected_class

        wait_result = manager.call_tool(
            "process",
            {
                "action": "wait",
                "session_id": start_result.value["session_id"],
                "timeout": 5,
            },
        )
        assert wait_result.success is True

        log_result = manager.call_tool(
            "process",
            {
                "action": "log",
                "session_id": start_result.value["session_id"],
                "limit": 20,
            },
        )
        assert log_result.success is True
        assert log_result.value["stdout"] != "" or log_result.value["stderr"] == ""

    stdin_cases = [
        (f"python '{script_path}'", "python_script"),
        (f'python "{script_path}"', "python_script"),
    ]

    for command, expected_class in stdin_cases:
        start_result = manager.call_tool(
            "terminal",
            {
                "command": command,
                "workdir": str(tmp_path),
                "timeout": 5,
                "background": True,
                "pty": True,
            },
        )
        assert start_result.success is True
        assert start_result.value["pty_capability_class"] == expected_class

        submit_result = manager.call_tool(
            "process",
            {
                "action": "submit",
                "session_id": start_result.value["session_id"],
                "data": "matrix-stdin",
            },
        )
        assert submit_result.success is True

        wait_result = manager.call_tool(
            "process",
            {
                "action": "wait",
                "session_id": start_result.value["session_id"],
                "timeout": 5,
            },
        )
        assert wait_result.success is True

        log_result = manager.call_tool(
            "process",
            {
                "action": "log",
                "session_id": start_result.value["session_id"],
                "limit": 20,
            },
        )
        assert log_result.success is True
        assert "matrix-stdin" in log_result.value["stdout"]


def test_background_terminal_task_with_watch_pattern_emits_midrun_notification(tmp_path):
    manager = build_tool_manager()

    start_result = manager.call_tool(
        "terminal",
        {
            "command": "python -c \"import time; print('booting'); print('WATCH-HIT'); time.sleep(0.2)\"",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "watch_patterns": ["WATCH-HIT"],
        },
    )
    assert start_result.success is True

    wait_result = manager.call_tool(
        "process",
        {
            "action": "wait",
            "session_id": start_result.value["session_id"],
            "timeout": 5,
        },
    )
    assert wait_result.success is True

    notifications_result = manager.call_tool("process", {"action": "notifications"})
    assert notifications_result.success is True
    matching = [
        item for item in notifications_result.value["notifications"]
        if item["session_id"] == start_result.value["session_id"] and item.get("event_type") == "watch_pattern_matched"
    ]
    assert len(matching) == 1
    assert matching[0]["pattern"] == "WATCH-HIT"
    assert "WATCH-HIT" in matching[0].get("stdout", "")


def test_background_terminal_task_without_pattern_match_emits_no_watch_notification(tmp_path):
    manager = build_tool_manager()

    start_result = manager.call_tool(
        "terminal",
        {
            "command": "python -c \"print('no-watch-hit')\"",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "watch_patterns": ["WATCH-HIT"],
        },
    )
    assert start_result.success is True

    wait_result = manager.call_tool(
        "process",
        {
            "action": "wait",
            "session_id": start_result.value["session_id"],
            "timeout": 5,
        },
    )
    assert wait_result.success is True

    notifications_result = manager.call_tool("process", {"action": "notifications"})
    assert notifications_result.success is True
    matching = [
        item for item in notifications_result.value["notifications"]
        if item["session_id"] == start_result.value["session_id"] and item.get("event_type") == "watch_pattern_matched"
    ]
    assert matching == []


def test_background_terminal_task_with_multiple_watch_patterns_emits_distinct_notifications(tmp_path):
    manager = build_tool_manager()

    start_result = manager.call_tool(
        "terminal",
        {
            "command": "python -c \"import time; print('ALPHA'); print('BETA'); time.sleep(0.2)\"",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "watch_patterns": ["ALPHA", "BETA"],
        },
    )
    assert start_result.success is True

    wait_result = manager.call_tool(
        "process",
        {
            "action": "wait",
            "session_id": start_result.value["session_id"],
            "timeout": 5,
        },
    )
    assert wait_result.success is True

    notifications_result = manager.call_tool("process", {"action": "notifications"})
    assert notifications_result.success is True
    matching = [
        item for item in notifications_result.value["notifications"]
        if item["session_id"] == start_result.value["session_id"] and item.get("event_type") == "watch_pattern_matched"
    ]
    patterns = {item["pattern"] for item in matching}
    assert patterns == {"ALPHA", "BETA"}


def test_background_terminal_task_repeated_same_pattern_still_emits_once_per_pattern(tmp_path):
    manager = build_tool_manager()

    start_result = manager.call_tool(
        "terminal",
        {
            "command": "python -c \"import time; print('ALPHA'); print('ALPHA'); time.sleep(0.2)\"",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "watch_patterns": ["ALPHA"],
        },
    )
    assert start_result.success is True

    wait_result = manager.call_tool(
        "process",
        {
            "action": "wait",
            "session_id": start_result.value["session_id"],
            "timeout": 5,
        },
    )
    assert wait_result.success is True

    notifications_result = manager.call_tool("process", {"action": "notifications"})
    assert notifications_result.success is True
    matching = [
        item for item in notifications_result.value["notifications"]
        if item["session_id"] == start_result.value["session_id"] and item.get("event_type") == "watch_pattern_matched"
    ]
    assert len(matching) == 1
    assert matching[0]["pattern"] == "ALPHA"


def test_process_poll_can_observe_background_pty_session(tmp_path):
    manager = build_tool_manager()

    start_result = manager.call_tool(
        "terminal",
        {
            "command": "sleep 1",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )

    assert start_result.success is False
    assert "session_id" in start_result.value

    poll_result = manager.call_tool(
        "process",
        {
            "action": "poll",
            "session_id": start_result.value["session_id"],
        },
    )

    assert poll_result.success is True
    assert poll_result.value["status"] == "blocked"
    assert poll_result.value["pty"] is True
    assert poll_result.value["session_type"] == "pty_host"
    assert poll_result.value["routing"] == "dedicated_host_required"
    assert poll_result.value["ordinary_pipe_process"] is False
    assert poll_result.value["host_kind"] == "placeholder"
    assert poll_result.value["host_state"] == "unimplemented"
    assert poll_result.value["host_controller_kind"] == "placeholder"


def test_process_list_includes_background_pty_placeholder_session_with_stable_shape(tmp_path):
    manager = build_tool_manager()

    start_result = manager.call_tool(
        "terminal",
        {
            "command": "sleep 1",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )

    assert start_result.success is False
    assert "session_id" in start_result.value

    list_result = manager.call_tool("process", {"action": "list"})

    assert list_result.success is True
    matching = [
        session
        for session in list_result.value["sessions"]
        if session["session_id"] == start_result.value["session_id"]
    ]
    assert len(matching) == 1

    session = matching[0]
    assert session["status"] == "blocked"
    assert session["pty"] is True
    assert session["session_type"] == "pty_host"
    assert session["routing"] == "dedicated_host_required"
    assert session["ordinary_pipe_process"] is False
    assert session["host_kind"] == "placeholder"
    assert session["host_state"] == "unimplemented"
    assert session["host_controller_kind"] == "placeholder"


def test_process_kill_handles_background_pty_session(tmp_path):
    manager = build_tool_manager()

    start_result = manager.call_tool(
        "terminal",
        {
            "command": "sleep 10",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )

    assert start_result.success is False
    assert "session_id" in start_result.value

    kill_result = manager.call_tool(
        "process",
        {
            "action": "kill",
            "session_id": start_result.value["session_id"],
        },
    )

    assert kill_result.success is True
    assert kill_result.value["status"] == "killed"
    assert kill_result.value["pty"] is True
    assert kill_result.value["session_type"] == "pty_host"
    assert kill_result.value["routing"] == "dedicated_host_required"
    assert kill_result.value["ordinary_pipe_process"] is False
    assert kill_result.value["host_kind"] == "placeholder"
    assert kill_result.value["host_state"] == "killed"
    assert kill_result.value["host_controller_kind"] == "placeholder"


def test_process_log_can_report_backend_limit_from_background_pty_session(tmp_path):
    manager = build_tool_manager()

    start_result = manager.call_tool(
        "terminal",
        {
            "command": "printf 'hello-from-pty\\n'",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )

    assert start_result.success is False
    assert "pty host" in start_result.error.lower() or "background pty" in start_result.error.lower()


def test_process_log_returns_stable_shape_for_background_pty_session(tmp_path):
    manager = build_tool_manager()

    start_result = manager.call_tool(
        "terminal",
        {
            "command": "sleep 1",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )

    assert start_result.success is False
    assert "session_id" in start_result.value

    log_result = manager.call_tool(
        "process",
        {
            "action": "log",
            "session_id": start_result.value["session_id"],
            "limit": 20,
        },
    )

    assert log_result.success is True
    assert log_result.value["status"] == "blocked"
    assert log_result.value["stdout"] == ""
    assert "pty host" in log_result.value["stderr"].lower() or "background pty" in log_result.value["stderr"].lower()


def test_process_wait_returns_stable_boundary_for_background_pty_placeholder_session(tmp_path):
    manager = build_tool_manager()

    start_result = manager.call_tool(
        "terminal",
        {
            "command": "sleep 1",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )

    assert start_result.success is False
    assert "session_id" in start_result.value

    wait_result = manager.call_tool(
        "process",
        {
            "action": "wait",
            "session_id": start_result.value["session_id"],
            "timeout": 1,
        },
    )

    assert wait_result.success is True
    assert wait_result.value["status"] == "blocked"
    assert wait_result.value["pty"] is True
    assert wait_result.value["session_type"] == "pty_host"
    assert wait_result.value["routing"] == "dedicated_host_required"
    assert wait_result.value["ordinary_pipe_process"] is False
    assert wait_result.value["host_kind"] == "placeholder"
    assert wait_result.value["host_state"] == "unimplemented"
    assert wait_result.value["host_controller_kind"] == "placeholder"


def test_process_log_real_output_for_double_quoted_python_script_is_available(tmp_path):
    manager = build_tool_manager()
    script_path = tmp_path / "pty_output_script.py"
    script_path.write_text("print('hello-from-pty-script')\n", encoding="utf-8")

    start_result = manager.call_tool(
        "terminal",
        {
            "command": f'python "{script_path}"',
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )

    assert start_result.success is True

    wait_result = manager.call_tool(
        "process",
        {
            "action": "wait",
            "session_id": start_result.value["session_id"],
            "timeout": 5,
        },
    )
    assert wait_result.success is True

    log_result = manager.call_tool(
        "process",
        {
            "action": "log",
            "session_id": start_result.value["session_id"],
            "limit": 20,
        },
    )
    assert log_result.success is True
    assert "hello-from-pty-script" in log_result.value["stdout"]


def test_double_quoted_python_script_is_reported_as_real_host_runner_success(tmp_path):
    manager = build_tool_manager()
    script_path = tmp_path / "pty_boundary_script.py"
    script_path.write_text("print('hello-from-pty-boundary')\n", encoding="utf-8")

    start_result = manager.call_tool(
        "terminal",
        {
            "command": f'python "{script_path}"',
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "pty": True,
        },
    )

    assert start_result.success is True
    assert start_result.value is not None
    assert start_result.value["pty"] is True
    assert start_result.value["session_type"] == "pty_host"
    assert start_result.value["routing"] == "dedicated_host_runner"
    assert start_result.value["ordinary_pipe_process"] is False
    assert start_result.value["host_kind"] == "runner"
    assert start_result.value["host_state"] in {"running", "exited"}
    assert start_result.value["host_controller_kind"] == "runner"
    assert start_result.value["pty_capability_class"] == "python_script"


def test_background_terminal_process_can_receive_stdin_via_submit(tmp_path):
    manager = build_tool_manager()

    start_result = manager.call_tool(
        "terminal",
        {
            "command": "python -c \"print(input())\"",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
        },
    )

    assert start_result.success is True
    session_id = start_result.value["session_id"]

    submit_result = manager.call_tool(
        "process",
        {
            "action": "submit",
            "session_id": session_id,
            "data": "hello from stdin",
        },
    )

    assert submit_result.success is True

    wait_result = manager.call_tool(
        "process",
        {
            "action": "wait",
            "session_id": session_id,
            "timeout": 5,
        },
    )

    assert wait_result.success is True

    log_result = manager.call_tool(
        "process",
        {
            "action": "log",
            "session_id": session_id,
            "limit": 20,
        },
    )

    assert log_result.success is True
    assert "hello from stdin" in log_result.value["stdout"]


def test_background_terminal_process_can_receive_stdin_via_write_and_close(tmp_path):
    manager = build_tool_manager()

    start_result = manager.call_tool(
        "terminal",
        {
            "command": "python -c \"import sys; data = sys.stdin.read(); print(data.upper())\"",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
        },
    )

    assert start_result.success is True
    session_id = start_result.value["session_id"]

    write_result = manager.call_tool(
        "process",
        {
            "action": "write",
            "session_id": session_id,
            "data": "abc",
        },
    )

    assert write_result.success is True

    close_result = manager.call_tool(
        "process",
        {
            "action": "close",
            "session_id": session_id,
        },
    )

    assert close_result.success is True

    second_write_result = manager.call_tool(
        "process",
        {
            "action": "write",
            "session_id": session_id,
            "data": "def",
        },
    )

    assert second_write_result.success is False
    assert "closed" in second_write_result.error.lower()

    wait_result = manager.call_tool(
        "process",
        {
            "action": "wait",
            "session_id": session_id,
            "timeout": 5,
        },
    )

    assert wait_result.success is True

    log_result = manager.call_tool(
        "process",
        {
            "action": "log",
            "session_id": session_id,
            "limit": 20,
        },
    )

    assert log_result.success is True
    assert "ABC" in log_result.value["stdout"]
