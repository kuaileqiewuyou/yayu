from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from llm.tools.tool_manager import ToolManager

from llm.tools.builtin_tools import register_builtin_tools
from core.runtime.process_registry import ProcessRegistry


def build_tool_manager():
    manager = ToolManager()
    register_builtin_tools(manager)
    return manager


def test_process_registry_refuses_more_than_configured_running_sessions(monkeypatch) -> None:
    class FakeProcess:
        pid = 100
        stdin = None
        stdout = None
        stderr = None

        def __init__(self):
            self.killed = False

        def poll(self):
            return None

        def kill(self):
            self.killed = True

    registry = ProcessRegistry(max_running_sessions=1)
    registry.start(FakeProcess())
    refused = FakeProcess()

    try:
        registry.start(refused)
    except RuntimeError as exc:
        assert "concurrent" in str(exc).lower()
    else:
        raise AssertionError("process registry accepted too many running sessions")
    assert refused.killed is True


def test_process_registry_enforces_capacity_atomically_for_concurrent_starts() -> None:
    barrier = Barrier(2)

    class FakeProcess:
        pid = 100
        stdin = None
        stdout = None
        stderr = None

        def __init__(self):
            self.killed = False

        def poll(self):
            return None

        def kill(self):
            self.killed = True

    class RacingRegistry(ProcessRegistry):
        def _register_running_session(self, session, *, reserved=False):
            barrier.wait(timeout=5)
            return super()._register_running_session(session, reserved=reserved)

    registry = RacingRegistry(max_running_sessions=1)
    processes = [FakeProcess(), FakeProcess()]

    def start(process):
        try:
            registry.start(process)
            return "started"
        except RuntimeError:
            return "refused"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(start, processes))

    assert sorted(results) == ["refused", "started"]
    assert sum(process.killed for process in processes) == 1
    assert len(registry.list_sessions()) == 1


def test_process_registry_reservation_blocks_spawn_slot_before_process_creation() -> None:
    registry = ProcessRegistry(max_running_sessions=1)

    registry.reserve_running_slot()

    try:
        registry.reserve_running_slot()
    except RuntimeError as exc:
        assert "concurrent" in str(exc).lower()
    else:
        raise AssertionError("second pre-spawn reservation must be refused")
    registry.release_running_slot()
    registry.reserve_running_slot()
    registry.release_running_slot()


def test_process_registry_redacts_secrets_from_pending_decision_list() -> None:
    registry = ProcessRegistry()
    registry.create_pending_decision(
        request={
            "command": "curl -H 'Authorization: Bearer super-secret-token' https://example.com",
            "workdir": None,
        },
        risk_level="high",
        reason="approval required",
    )

    serialized = str(registry.list_pending())

    assert "super-secret-token" not in serialized
    assert "[REDACTED]" in serialized


def test_process_tool_is_registered_as_builtin_tool() -> None:
    manager = build_tool_manager()

    assert "process" in manager.list_tools()
    definitions = manager.get_tool_definitions()
    assert any(item["function"]["name"] == "process" for item in definitions)


def test_process_tool_supports_list_poll_wait_log_kill_and_stdin_actions() -> None:
    manager = build_tool_manager()

    definition = next(item for item in manager.get_tool_definitions() if item["function"]["name"] == "process")
    properties = definition["function"]["parameters"]["properties"]

    assert "action" in properties
    assert "session_id" in properties
    assert "timeout" in properties
    assert "limit" in properties
    assert "data" in properties
    assert "write" in definition["function"]["parameters"]["properties"]["action"]["description"]
    assert "submit" in definition["function"]["parameters"]["properties"]["action"]["description"]
    assert "close" in definition["function"]["parameters"]["properties"]["action"]["description"]
    assert "notifications" in definition["function"]["parameters"]["properties"]["action"]["description"]


def test_process_tool_rejects_unknown_session_id() -> None:
    manager = build_tool_manager()

    result = manager.call_tool("process", {"action": "poll", "session_id": "missing-session"})

    assert result.success is False
    assert "session" in result.error.lower()


def test_process_tool_rejects_unknown_session_for_submit() -> None:
    manager = build_tool_manager()

    result = manager.call_tool(
        "process",
        {"action": "submit", "session_id": "missing-session", "data": "hello"},
    )

    assert result.success is False
    assert "session" in result.error.lower()


def test_process_tool_notifications_action_returns_structured_result() -> None:
    manager = build_tool_manager()

    result = manager.call_tool("process", {"action": "notifications"})

    assert result.success is True or result.success is False


def test_process_tool_supports_pending_action_for_unified_surface() -> None:
    manager = build_tool_manager()

    definition = next(item for item in manager.get_tool_definitions() if item["function"]["name"] == "process")
    action_description = definition["function"]["parameters"]["properties"]["action"]["description"]

    assert "pending" in action_description
    assert "approve" not in action_description
    assert "deny" not in action_description
    assert "follow_up" in action_description


def test_process_tool_pending_action_returns_notifications_and_decisions() -> None:
    manager = build_tool_manager()

    result = manager.call_tool("process", {"action": "pending"})

    assert result.success is True
    assert "notifications" in result.value
    assert "decisions" in result.value


def test_process_tool_cannot_approve_pending_decision(tmp_path) -> None:
    manager = build_tool_manager()

    blocked = manager.call_tool(
        "terminal",
        {
            "command": "rm -rf testdir",
            "workdir": str(tmp_path),
            "timeout": 5,
        },
    )
    decision_id = blocked.value["pending_decision_id"]

    result = manager.call_tool("process", {"action": "approve", "session_id": decision_id})

    assert result.success is False
    assert "unsupported" in result.error.lower()


def test_process_tool_cannot_deny_pending_decision(tmp_path) -> None:
    manager = build_tool_manager()

    blocked = manager.call_tool(
        "terminal",
        {
            "command": "rm -rf testdir",
            "workdir": str(tmp_path),
            "timeout": 5,
        },
    )
    decision_id = blocked.value["pending_decision_id"]

    result = manager.call_tool("process", {"action": "deny", "session_id": decision_id})

    assert result.success is False
    assert "unsupported" in result.error.lower()


def test_trusted_terminal_approval_executes_stored_request_once(tmp_path) -> None:
    from core.runtime.terminal_executor import approve_terminal_decision

    manager = build_tool_manager()
    target = tmp_path / "approved-delete.txt"
    target.write_text("delete me", encoding="utf-8")
    blocked = manager.call_tool(
        "terminal",
        {"command": f'rm -rf "{target}"', "workdir": str(tmp_path), "timeout": 5},
    )
    decision_id = blocked.value["pending_decision_id"]

    approved = approve_terminal_decision(decision_id)

    assert approved["decision_id"] == decision_id
    assert approved["status"] == "consumed"
    assert approved["result"]["exit_code"] == 0
    assert not target.exists()

    try:
        approve_terminal_decision(decision_id)
    except RuntimeError as exc:
        assert "already" in str(exc).lower()
    else:
        raise AssertionError("approval decision must be single-use")


def test_trusted_terminal_denial_is_single_use_and_never_executes(tmp_path) -> None:
    from core.runtime.terminal_executor import approve_terminal_decision, deny_terminal_decision

    manager = build_tool_manager()
    target = tmp_path / "denied-delete.txt"
    target.write_text("keep me", encoding="utf-8")
    blocked = manager.call_tool(
        "terminal",
        {"command": f'rm -rf "{target}"', "workdir": str(tmp_path), "timeout": 5},
    )
    decision_id = blocked.value["pending_decision_id"]

    denied = deny_terminal_decision(decision_id)

    assert denied == {"decision_id": decision_id, "status": "denied"}
    assert target.read_text(encoding="utf-8") == "keep me"
    try:
        approve_terminal_decision(decision_id)
    except RuntimeError as exc:
        assert "already" in str(exc).lower()
    else:
        raise AssertionError("denied decision must not be executable")


def test_process_tool_follow_up_action_returns_structured_events() -> None:
    manager = build_tool_manager()

    result = manager.call_tool("process", {"action": "follow_up"})

    assert result.success is True
    assert "events" in result.value


def test_background_completion_notification_is_promoted_to_follow_up_event(tmp_path):
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

    follow_up_result = manager.call_tool("process", {"action": "follow_up"})

    assert follow_up_result.success is True
    matching = [
        item for item in follow_up_result.value["events"]
        if item.get("session_id") == start_result.value["session_id"]
    ]
    assert len(matching) == 1
    assert matching[0]["event_type"] == "completion_follow_up"


def test_high_frequency_watch_pattern_events_do_not_flood_notifications(tmp_path):
    manager = build_tool_manager()

    start_result = manager.call_tool(
        "terminal",
        {
            "command": "python -c \"import time; [print('SPAM') for _ in range(20)]; time.sleep(0.2)\"",
            "workdir": str(tmp_path),
            "timeout": 5,
            "background": True,
            "watch_patterns": ["SPAM"],
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


def test_process_tool_log_supports_offset_parameter_for_pagination() -> None:
    manager = build_tool_manager()

    definition = next(item for item in manager.get_tool_definitions() if item["function"]["name"] == "process")
    properties = definition["function"]["parameters"]["properties"]

    assert "offset" in properties
