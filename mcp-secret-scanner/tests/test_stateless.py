"""Proves the server is stateless: no session id, and every request stands alone."""

import json
from contextlib import asynccontextmanager

import httpx

import server

HEADERS = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}


# Not a fixture: the app's lifespan must start and stop in the same task.
@asynccontextmanager
async def mcp_client():
    app = server.streamable_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8003") as c:
            yield c


def call(name, arguments, id=1):
    return {"jsonrpc": "2.0", "id": id, "method": "tools/call", "params": {"name": name, "arguments": arguments}}


async def test_initialize_returns_no_session_id():
    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
    }
    async with mcp_client() as client:
        resp = await client.post("/mcp", json=init, headers=HEADERS)
    assert resp.status_code == 200
    assert "mcp-session-id" not in resp.headers
    assert resp.headers["content-type"].startswith("application/json")  # one plain JSON answer, no event stream


async def test_tool_call_works_without_initialize():
    async with mcp_client() as client:
        resp = await client.post("/mcp", json=call("redact_secrets", {"text": "pwd = 'Sup3rS3cret!'"}), headers=HEADERS)
    body = resp.json()
    assert resp.status_code == 200, resp.text
    assert body["result"]["content"][0]["text"] == "pwd = '[REDACTED:password_assignment]'"


async def test_scan_returns_structured_findings():
    async with mcp_client() as client:
        resp = await client.post("/mcp", json=call("scan_secrets", {"text": "a\nkey = AKIAIOSFODNN7EXAMPLE"}), headers=HEADERS)
    result = resp.json()["result"]["structuredContent"]
    assert result["found"] == 1
    assert result["findings"][0]["type"] == "aws_access_key"
    assert result["findings"][0]["line"] == 2


async def test_requests_are_independent():
    # Two calls on the same HTTP client, with no session header between them: each is answered on its own.
    async with mcp_client() as client:
        first = await client.post("/mcp", json=call("scan_secrets", {"text": "clean"}, id=1), headers=HEADERS)
        second = await client.post("/mcp", json=call("scan_secrets", {"text": "pwd = 'Sup3rS3cret!'"}, id=2), headers=HEADERS)
    assert first.json()["result"]["structuredContent"]["found"] == 0
    assert second.json()["result"]["structuredContent"]["found"] == 1


async def test_lists_both_tools():
    async with mcp_client() as client:
        resp = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=HEADERS)
    assert sorted(t["name"] for t in resp.json()["result"]["tools"]) == ["redact_secrets", "scan_secrets"]
    assert json.dumps(resp.json())  # plain JSON body
