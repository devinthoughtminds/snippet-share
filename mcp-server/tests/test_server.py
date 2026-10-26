import functools
import json

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

import server


def fake_api(monkeypatch, handler):
    # Route the server's HTTP calls to `handler` instead of a real snippet-share API.
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        server.httpx, "AsyncClient", functools.partial(real_client, transport=httpx.MockTransport(handler))
    )


async def test_returns_share_url(monkeypatch):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "abc", "share_url": "http://localhost:3000/view/abc", "created_at": "x"})

    fake_api(monkeypatch, handler)

    assert await server.share_snippet("print('hi')") == "http://localhost:3000/view/abc"
    assert seen == {"url": "http://localhost:8000/api/v1/pastes", "body": {"text": "print('hi')"}}


async def test_api_rejection_is_reported(monkeypatch):
    fake_api(monkeypatch, lambda request: httpx.Response(413, json={"detail": "Paste exceeds 1 MB"}))

    with pytest.raises(ToolError, match="Paste exceeds 1 MB"):
        await server.share_snippet("x")


async def test_api_down_is_reported(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("refused")

    fake_api(monkeypatch, handler)

    with pytest.raises(ToolError, match="Is the app running"):
        await server.share_snippet("x")


async def test_tool_is_registered():
    tools = await server.mcp.list_tools()
    assert [t.name for t in tools] == ["share_snippet"]
