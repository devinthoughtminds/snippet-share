import json
import os
import subprocess
import sys
import time
from types import MappingProxyType

from langfuse.types import MaskOtelSpansParams, OtelSpanData, OtelSpanIdentifier

from snippet_tracing import mask_spans, redact_value

AWS = "AKIA" + "IOSFODNN7EXAMPLE"
GITHUB = "ghp_" + "a" * 36
PEM = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAu1SU1LfVLPHC\nozMxH2Mo4lgOEePzNm0tRgeLezV6\n-----END RSA PRIVATE KEY-----"


def _run(code: str, **env) -> subprocess.CompletedProcess:
    clean = {k: v for k, v in os.environ.items() if not k.startswith("LANGFUSE_")}
    return subprocess.run([sys.executable, "-c", code], env={**clean, **env}, capture_output=True, text=True, timeout=60)


def test_redact_value_plain_text():
    assert "[REDACTED:aws_access_key]" in redact_value(f'key = "{AWS}"')


def test_redact_value_handles_json_with_multiline_key():
    out = json.loads(redact_value(json.dumps({"args": {"text": PEM}})))
    assert "[REDACTED:private_key]" in out["args"]["text"]
    assert "MIIEow" not in json.dumps(out)


def test_mask_spans_handles_non_string_and_sequence_attributes():
    ident = OtelSpanIdentifier(trace_id="a" * 32, span_id="b" * 16)
    span = OtelSpanData(
        trace_id=ident.trace_id, span_id=ident.span_id, parent_span_id=None, name="s",
        instrumentation_scope_name="t", instrumentation_scope_version=None,
        attributes=MappingProxyType({"n": 3, "b": True, "s": AWS, "seq": ("ok", AWS)}),
        resource_attributes=MappingProxyType({}),
    )
    patch = mask_spans(params=MaskOtelSpansParams(spans={ident: span})).span_patches[ident]
    assert set(patch.set_attributes) == {"s", "seq"}
    assert patch.set_attributes["s"] == "[REDACTED:aws_access_key]"
    assert patch.set_attributes["seq"] == ("ok", "[REDACTED:aws_access_key]")


def test_mask_spans_leaves_clean_spans_alone():
    ident = OtelSpanIdentifier(trace_id="a" * 32, span_id="b" * 16)
    span = OtelSpanData(ident.trace_id, ident.span_id, None, "s", "t", None, MappingProxyType({"s": "hello"}), MappingProxyType({}))
    assert ident not in mask_spans(params=MaskOtelSpansParams(spans={ident: span})).span_patches


def test_redact_value_on_1mb_is_fast():
    chunk = "def handler(event, context):\n    return {'status': 200, 'body': event['body']}\n"
    filler = chunk * (1_000_000 // len(chunk) // 3)
    text = filler + f'aws = "{AWS}"\n' + filler + f"token = '{GITHUB}'\n" + filler + "DB_PASSWORD=Sup3rS3cretValue\n"
    start = time.perf_counter()
    out = redact_value(text)
    assert time.perf_counter() - start < 2
    assert AWS not in out and GITHUB not in out and "Sup3rS3cretValue" not in out


def test_exported_span_is_masked(exporter):
    from langfuse import get_client

    with get_client().start_as_current_observation(name="t", input=f"token = '{GITHUB}'"):
        pass
    get_client().flush()
    attrs = json.dumps([dict(s.attributes) for s in exporter.get_finished_spans()])
    assert "ghp_" not in attrs
    assert "[REDACTED:github_token]" in attrs


def test_traced_tool_works_when_langfuse_is_unreachable():
    code = (
        "import snippet_tracing as t\n"
        "assert t.init_tracing()\n"
        "@t.traced('x')\n"
        "def tool(): return 'ok'\n"
        "print(tool())\n"
        "from langfuse import get_client; get_client().flush()\n"
    )
    r = _run(code, LANGFUSE_PUBLIC_KEY="pk-lf-test", LANGFUSE_SECRET_KEY="sk-lf-test", LANGFUSE_BASE_URL="http://127.0.0.1:9")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "ok"


def test_disabled_without_keys():
    r = _run("import snippet_tracing as t; print(t.init_tracing())")
    assert r.stdout.strip() == "False"
    assert r.stderr == ""


def test_mcp_client_tool_call_span_is_exported(exporter):
    # The MCP client's "MCP send tools/call" span is the parent of the server's span; without it the server work floats loose.
    from langfuse import get_client
    from opentelemetry import trace

    tracer = trace.get_tracer("mcp-python-sdk")
    with tracer.start_as_current_span("MCP send tools/call scan_secrets"):
        pass
    with tracer.start_as_current_span("MCP send tools/list"):
        pass
    get_client().flush()
    names = [s.name for s in exporter.get_finished_spans()]
    assert "MCP send tools/call scan_secrets" in names
    assert "MCP send tools/list" not in names


def test_error_status_and_events_are_masked(exporter):
    # A tool error often echoes its input (e.g. the API's 422 detail); it must not reach Langfuse unmasked.
    import pytest
    from langfuse import get_client
    from opentelemetry import trace

    from snippet_tracing import traced

    @traced("failing_tool")
    def failing_tool():
        raise ValueError(f"rejected: aws = '{AWS}'")

    with pytest.raises(ValueError):
        failing_tool()
    with trace.get_tracer("openinference.instrumentation.google_adk").start_as_current_span("t") as span:
        span.record_exception(ValueError(f"token = '{GITHUB}'"))
    get_client().flush()

    spans = exporter.get_finished_spans()
    exported = json.dumps([[s.status.description, [dict(e.attributes) for e in s.events]] for s in spans])
    assert "failing_tool" in [s.name for s in spans]
    assert AWS not in exported and GITHUB not in exported
    assert "[REDACTED:aws_access_key]" in exported and "[REDACTED:github_token]" in exported


def test_redact_value_handles_nested_json_and_string_literals():
    env_line = "x = 1\nDB_PASSWORD=Sup3rS3cretValue"
    for encoded in (json.dumps({"args": json.dumps({"text": env_line})}), json.dumps(env_line)):
        out = redact_value(encoded)
        assert "Sup3rS3cretValue" not in out, encoded
        assert "[REDACTED:env_secret]" in out


def test_redact_value_leaves_clean_json_byte_for_byte():
    assert redact_value('{"a":1,"b":["x"]}') == '{"a":1,"b":["x"]}'
