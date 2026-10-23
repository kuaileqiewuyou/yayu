from core.mcp.registry import build_mcp_tool_definition, namespace_mcp_tool_name


def test_namespace_mcp_tool_name_prefixes_server_name() -> None:
    assert namespace_mcp_tool_name("filesystem", "read_file") == "filesystem.read_file"


def test_build_mcp_tool_definition_converts_schema_to_openai_function_tool() -> None:
    tool = {
        "name": "read_file",
        "description": "Read a file from disk",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to file"},
            },
            "required": ["path"],
        },
    }

    definition = build_mcp_tool_definition("filesystem", tool)

    assert definition == {
        "type": "function",
        "function": {
            "name": "filesystem.read_file",
            "description": "Read a file from disk",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to file"},
                },
                "required": ["path"],
            },
        },
    }


def test_build_mcp_tool_definition_uses_empty_schema_when_missing_input_schema() -> None:
    tool = {
        "name": "ping",
        "description": "Ping the MCP server",
    }

    definition = build_mcp_tool_definition("system", tool)

    assert definition["function"]["name"] == "system.ping"
    assert definition["function"]["parameters"] == {
        "type": "object",
        "properties": {},
    }
