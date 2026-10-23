from llm.tools.tool_manager import ToolExecutionResult, ToolManager


class FakeMCPSession:
    def __init__(self):
        self.calls = []

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {"content": [{"type": "text", "text": f"called:{name}"}]}


class FailingMCPSession:
    def __init__(self, message="bridge closed"):
        self.calls = []
        self.message = message

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        raise RuntimeError(self.message)


def test_tool_manager_can_register_mcp_tool_definition() -> None:
    manager = ToolManager()
    session = FakeMCPSession()

    manager.register_mcp_tool(
        server_name="filesystem",
        tool_name="read_file",
        session=session,
        description="Read a file from disk",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )

    assert manager.list_tools() == ["filesystem.read_file"]
    definitions = manager.get_tool_definitions()
    assert definitions == [
        {
            "type": "function",
            "function": {
                "name": "filesystem.read_file",
                "description": "Read a file from disk",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }
    ]


def test_tool_manager_calls_registered_mcp_tool() -> None:
    manager = ToolManager()
    session = FakeMCPSession()

    manager.register_mcp_tool(
        server_name="filesystem",
        tool_name="read_file",
        session=session,
        description="Read a file from disk",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )

    result = manager.call_tool("filesystem.read_file", {"path": "README.md"})

    assert session.calls == [("read_file", {"path": "README.md"})]
    assert result == ToolExecutionResult(
        success=True,
        value={"content": [{"type": "text", "text": "called:read_file"}]},
    )


def test_tool_manager_returns_structured_failure_for_unknown_tool() -> None:
    manager = ToolManager()

    result = manager.call_tool("missing.tool", {"path": "README.md"})

    assert result == ToolExecutionResult(success=False, error="Tool missing.tool does not exist")


def test_tool_manager_reports_mcp_call_failure_to_callback() -> None:
    manager = ToolManager()
    session = FailingMCPSession("bridge closed")
    reported = []

    manager.register_mcp_tool(
        server_name="filesystem",
        tool_name="read_file",
        session=session,
        description="Read a file from disk",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        on_call_failure=lambda error: reported.append(error),
    )

    result = manager.call_tool("filesystem.read_file", {"path": "README.md"})

    assert session.calls == [("read_file", {"path": "README.md"})]
    assert result == ToolExecutionResult(success=False, error="bridge closed")
    assert reported == ["bridge closed"]


def test_tool_manager_passthroughs_tool_execution_result_without_double_wrapping() -> None:
    manager = ToolManager()

    def structured_failure_tool() -> ToolExecutionResult:
        return ToolExecutionResult(
            success=False,
            value={"placeholder": True, "path": "pty_host"},
            error="structured failure",
        )

    manager.register("structured_failure", structured_failure_tool)

    result = manager.call_tool("structured_failure", {})

    assert result == ToolExecutionResult(
        success=False,
        value={"placeholder": True, "path": "pty_host"},
        error="structured failure",
    )
