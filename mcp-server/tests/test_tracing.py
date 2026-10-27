"""With Langfuse keys set, share_snippet is traced, masked, and records failures. Without keys, test_server.py covers it unchanged."""

import importlib
import json

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

import server
from test_server import fake_api

AWS = "AKIA" + "IOSFODNN7EXAMPLE"
_EXPORTER = InMemorySpanExporter()  # the Langfuse client is a per-process singleton: one exporter for the run


@pytest.fixture
def exporter(monkeypatch):
    import snippet_tracing

    for k, v in {"LANGFUSE_PUBLIC_KEY": "pk-lf-test", "LANGFUSE_SECRET_KEY": "sk-lf-test", "LANGFUSE_BASE_URL": "http://127.0.0.1:9"}.items():
        monkeypatch.setenv(k, v)
    snippet_tracing.init_tracing(_EXPORTER)
    importlib.reload(server)  # traced() decides at decoration time
    _EXPORTER.clear()
    yield _EXPORTER
    _EXPORTER.clear()


def _share_spans(exporter):
    from langfuse import get_client

    get_client().flush()
    return [s for s in exporter.get_finished_spans() if s.name == "share_snippet"]


async def test_share_span_is_masked(monkeypatch, exporter):
    fake_api(monkeypatch, lambda r: httpx.Response(201, json={"id": "a", "share_url": "http://localhost:3000/view/a", "created_at": "x"}))
    await server.share_snippet(f'aws = "{AWS}"')
    spans = _share_spans(exporter)
    assert spans
    exported = json.dumps([dict(s.attributes) for s in spans])
    assert "AKIA" not in exported
    assert "[REDACTED:aws_access_key]" in exported


async def test_share_failure_is_on_the_span(monkeypatch, exporter):
    fake_api(monkeypatch, lambda r: httpx.Response(413, json={"detail": "Paste exceeds 1 MB"}))
    with pytest.raises(ToolError, match="Paste exceeds 1 MB"):
        await server.share_snippet("x")
    [span] = _share_spans(exporter)
    assert span.status.status_code == StatusCode.ERROR
    assert "413" in (span.status.description or "") + json.dumps(dict(span.attributes))


def test_tool_is_traced_when_server_starts_with_keys():
    # The way `python server.py` runs it: keys in the env, a fresh import, no reload.
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if not k.startswith("LANGFUSE_")}
    env.update(LANGFUSE_PUBLIC_KEY="pk-lf-test", LANGFUSE_SECRET_KEY="sk-lf-test", LANGFUSE_BASE_URL="http://127.0.0.1:9")
    r = subprocess.run([sys.executable, "-c", "import server; print(hasattr(server.share_snippet, '__wrapped__'))"],
                       env=env, capture_output=True, text=True, timeout=60)
    assert r.stdout.strip() == "True", r.stderr
