from core.mcp.status import MCPServerStatus, MCPStatusSnapshot, summarize_mcp_status


def test_empty_snapshot_reports_disabled_state() -> None:
    snapshot = MCPStatusSnapshot(state="disabled", servers=[])

    assert snapshot.state == "disabled"
    assert snapshot.servers == []


def test_snapshot_becomes_ready_when_all_enabled_servers_are_ready() -> None:
    snapshot = summarize_mcp_status(
        [
            MCPServerStatus(
                name="filesystem",
                transport="stdio",
                enabled=True,
                state="ready",
                tool_count=2,
            ),
            MCPServerStatus(
                name="remote-api",
                transport="http",
                enabled=True,
                state="ready",
                tool_count=1,
            ),
        ]
    )

    assert snapshot.state == "ready"
    assert [server.state for server in snapshot.servers] == ["ready", "ready"]


def test_snapshot_becomes_partial_when_ready_and_failed_servers_mix() -> None:
    snapshot = summarize_mcp_status(
        [
            MCPServerStatus(
                name="filesystem",
                transport="stdio",
                enabled=True,
                state="ready",
                tool_count=2,
            ),
            MCPServerStatus(
                name="remote-api",
                transport="http",
                enabled=True,
                state="discover_failed",
                error="auth failed",
            ),
        ]
    )

    assert snapshot.state == "partial"
    assert snapshot.servers[1].state == "discover_failed"
    assert snapshot.servers[1].error == "auth failed"


def test_snapshot_becomes_failed_when_all_enabled_servers_fail() -> None:
    snapshot = summarize_mcp_status(
        [
            MCPServerStatus(
                name="filesystem",
                transport="stdio",
                enabled=True,
                state="start_failed",
                error="process spawn failed",
            ),
            MCPServerStatus(
                name="remote-api",
                transport="http",
                enabled=True,
                state="discover_failed",
                error="auth failed",
            ),
        ]
    )

    assert snapshot.state == "failed"


def test_snapshot_supports_runtime_disconnect_state() -> None:
    snapshot = summarize_mcp_status(
        [
            MCPServerStatus(
                name="filesystem",
                transport="stdio",
                enabled=True,
                state="disconnected",
                error="bridge closed",
            )
        ]
    )

    assert snapshot.state == "failed"
    assert snapshot.servers[0].state == "disconnected"
    assert snapshot.servers[0].error == "bridge closed"
