from core.mcp.transport_stdio import build_stdio_transport
from core.mcp.config import MCPServerConfig


class FakePopen:
    def __init__(self, command, stdin=None, stdout=None, stderr=None, text=None):
        self.command = command
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.text = text
        self.terminated = False

    def terminate(self):
        self.terminated = True


class FakeBridge:
    def __init__(self, process):
        self.process = process
        self.started = False
        self.closed = False
        self.requests = []

    def start(self):
        self.started = True

    def request(self, method, params=None):
        self.requests.append((method, params))
        if method == "initialize":
            return {"protocolVersion": "2024-11-05"}
        return {}

    def close(self):
        self.closed = True


def test_build_stdio_transport_starts_subprocess_with_expected_command(monkeypatch) -> None:
    popen_calls = []

    def fake_popen(command, stdin=None, stdout=None, stderr=None, text=None):
        process = FakePopen(command, stdin=stdin, stdout=stdout, stderr=stderr, text=text)
        popen_calls.append(process)
        return process

    def fake_bridge_factory(process):
        return FakeBridge(process)

    config = MCPServerConfig(
        name="filesystem",
        transport="stdio",
        command="python",
        args=["tools/filesystem_server.py", "--debug"],
        enabled=True,
    )

    transport = build_stdio_transport(
        config,
        popen_factory=fake_popen,
        bridge_factory=fake_bridge_factory,
    )

    assert popen_calls[0].command == ["python", "tools/filesystem_server.py", "--debug"]
    transport.start()
    assert transport.bridge.started is True


def test_build_stdio_transport_raises_readable_error_when_process_spawn_fails() -> None:
    def fake_popen(command, stdin=None, stdout=None, stderr=None, text=None):
        raise OSError("spawn failed")

    config = MCPServerConfig(
        name="filesystem",
        transport="stdio",
        command="python",
        args=["tools/filesystem_server.py"],
        enabled=True,
    )

    try:
        build_stdio_transport(config, popen_factory=fake_popen)
    except RuntimeError as exc:
        assert "filesystem" in str(exc)
        assert "spawn failed" in str(exc)
    else:
        raise AssertionError("expected RuntimeError when MCP subprocess spawn fails")
