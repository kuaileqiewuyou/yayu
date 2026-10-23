import json

from core.mcp.config import MCPServerConfig
from core.mcp.transport_http import build_http_transport


class FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload.encode("utf-8")


def test_build_http_transport_posts_jsonrpc_initialize_and_list_tools() -> None:
    requests = []

    def fake_urlopen(request, timeout=None):
        requests.append(
            {
                "url": request.full_url,
                "timeout": timeout,
                "headers": dict(request.header_items()),
                "body": request.data.decode("utf-8"),
            }
        )
        body = requests[-1]["body"]
        if '"method": "initialize"' in body:
            return FakeHTTPResponse('{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}')
        if '"method": "notifications/initialized"' in body:
            return FakeHTTPResponse('{"jsonrpc":"2.0","id":2,"result":{}}')
        return FakeHTTPResponse('{"jsonrpc":"2.0","id":3,"result":{"tools":[{"name":"ping"}]}}')

    config = MCPServerConfig(
        name="remote-api",
        transport="http",
        url="http://127.0.0.1:8080/mcp",
        headers={"Authorization": "Bearer token"},
        enabled=True,
    )

    transport = build_http_transport(config, request_opener=fake_urlopen)
    tools = transport.list_tools()

    assert len(requests) == 3
    assert requests[0]["url"] == "http://127.0.0.1:8080/mcp"
    assert requests[0]["timeout"] == 120
    assert requests[0]["headers"]["Authorization"] == "Bearer token"
    assert json.loads(requests[0]["body"])["params"]["clientInfo"] == {"name": "yayu", "version": "v1"}
    assert tools == [{"name": "ping"}]


def test_build_http_transport_raises_readable_error_on_request_failure() -> None:
    def fake_urlopen(request, timeout=None):
        raise OSError("connection refused")

    config = MCPServerConfig(
        name="remote-api",
        transport="http",
        url="http://127.0.0.1:8080/mcp",
        enabled=True,
    )

    transport = build_http_transport(config, request_opener=fake_urlopen)

    try:
        transport.list_tools()
    except RuntimeError as exc:
        assert "remote-api" in str(exc)
        assert "connection refused" in str(exc)
    else:
        raise AssertionError("expected RuntimeError when MCP HTTP request fails")
