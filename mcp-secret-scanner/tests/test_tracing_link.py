"""The scanner's tool span joins the calling agent's trace, through the W3C traceparent the agent puts in _meta."""

import importlib
import json

import httpx

AWS = "AKIA" + "IOSFODNN7EXAMPLE"
HEADERS = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}
TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"


async def test_tool_span_joins_callers_trace(exporter):
    import server

    importlib.reload(server)  # traced() decides at decoration time, so decorate again now tracing is on
    app = server.streamable_app()
    body = {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "scan_secrets", "arguments": {"text": f'aws = "{AWS}"'},
                   "_meta": {"traceparent": f"00-{TRACE_ID}-00f067aa0ba902b7-01"}},
    }
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8003") as c:
            resp = await c.post("/mcp", json=body, headers=HEADERS)
    assert resp.status_code == 200, resp.text

    from langfuse import get_client

    get_client().flush()
    spans = exporter.get_finished_spans()
    assert any(format(s.context.trace_id, "032x") == TRACE_ID for s in spans)
    assert any(s.name == "scan_secrets" for s in spans)
    exported = json.dumps([dict(s.attributes) for s in spans])
    assert AWS not in exported  # the masked preview "AKIA... (20 chars)" is allowed; the key itself is not
    assert "[REDACTED:aws_access_key]" in exported


def test_tools_are_traced_when_server_starts_with_keys():
    # The way `python server.py` runs it: keys in the env, a fresh import, no reload.
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if not k.startswith("LANGFUSE_")}
    env.update(LANGFUSE_PUBLIC_KEY="pk-lf-test", LANGFUSE_SECRET_KEY="sk-lf-test", LANGFUSE_BASE_URL="http://127.0.0.1:9")
    code = "import server; print(hasattr(server.scan_secrets, '__wrapped__'), hasattr(server.redact_secrets, '__wrapped__'))"
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    assert r.stdout.strip() == "True True", r.stderr
