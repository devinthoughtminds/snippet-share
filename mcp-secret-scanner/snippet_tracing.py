"""Optional Langfuse tracing shared by the agent and both MCP servers, with every exported span masked by redact().

Off unless LANGFUSE_PUBLIC_KEY is set: then nothing is created and traced() changes nothing.
"""

import json
import os

from scanner import redact

ENABLED = False


def redact_value(value: str) -> str:
    # Tool arguments arrive JSON-encoded, sometimes twice; redact the decoded strings so escaped newlines
    # (a PEM key, a .env line) still match. Clean JSON comes back unchanged, byte for byte.
    if value.lstrip()[:1] in ("{", "[", '"'):
        try:
            data = json.loads(value)
        except ValueError:
            pass
        else:
            redacted = _redact_json(data)
            return value if redacted == data else json.dumps(redacted, ensure_ascii=False)
    return redact(value)


def _redact_json(data):
    if isinstance(data, str):
        return redact_value(data)
    if isinstance(data, dict):
        return {k: _redact_json(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_redact_json(v) for v in data]
    return data


def _masked(value):
    """The attribute value with secrets redacted, or None when nothing changed (or it isn't text)."""
    if isinstance(value, str):
        new = redact_value(value)
        return new if new != value else None
    if isinstance(value, (list, tuple)) and value and all(isinstance(v, str) for v in value):
        new = tuple(redact_value(v) for v in value)
        return new if new != tuple(value) else None
    return None


def mask_spans(*, params):
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

    patches = {}
    for ident, span in params.spans.items():
        changed = {k: new for k, v in span.attributes.items() if (new := _masked(v)) is not None}
        if changed:
            patches[ident] = OtelSpanPatch(set_attributes=changed)
    return MaskOtelSpansResult(span_patches=patches)


def _redacting_exporter(inner):
    """mask_spans can only patch attributes. This also redacts the status message and event attributes
    (exception messages often echo a tool's input), right before spans are sent."""
    from opentelemetry.sdk.trace import Event, ReadableSpan
    from opentelemetry.sdk.trace.export import SpanExporter
    from opentelemetry.trace import Status

    def scrub(span):
        desc = span.status.description
        events = [Event(e.name, {k: _masked(v) or v for k, v in (e.attributes or {}).items()}, e.timestamp) for e in span.events]
        return ReadableSpan(
            name=span.name, context=span.context, parent=span.parent, resource=span.resource,
            attributes=span.attributes, events=events, links=span.links, kind=span.kind,
            status=Status(span.status.status_code, redact(desc)) if desc else span.status,
            start_time=span.start_time, end_time=span.end_time, instrumentation_scope=span.instrumentation_scope,
        )

    class RedactingExporter(SpanExporter):
        def export(self, spans):
            return inner.export([scrub(s) for s in spans])

        def shutdown(self):
            inner.shutdown()

        def force_flush(self, timeout_millis=30000):
            return inner.force_flush(timeout_millis)

    return RedactingExporter()


def _langfuse_otlp_exporter():
    # shortcut: mirrors Langfuse 4.15's default exporter (span_processor.py) so it can be wrapped; recheck on upgrade.
    import base64

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    pk, sk = os.environ["LANGFUSE_PUBLIC_KEY"], os.environ.get("LANGFUSE_SECRET_KEY", "")
    base = (os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST") or "https://cloud.langfuse.com").rstrip("/")
    auth = "Basic " + base64.b64encode(f"{pk}:{sk}".encode()).decode("ascii")
    return OTLPSpanExporter(
        endpoint=f"{base}/api/public/otel/v1/traces",
        headers={"Authorization": auth, "x-langfuse-sdk-name": "python", "x-langfuse-public-key": pk},
        timeout=int(os.environ.get("LANGFUSE_TIMEOUT", "5")),
    )


def export_span(span) -> bool:
    """Langfuse's default spans, plus the MCP client's tool-call span: it is the parent of the server's span."""
    from langfuse import is_default_export_span

    scope = span.instrumentation_scope.name if span.instrumentation_scope else ""
    return is_default_export_span(span) or (scope == "mcp-python-sdk" and span.name.startswith("MCP send tools/call"))


def init_tracing(span_exporter=None) -> bool:
    """Start the Langfuse exporter when keys are set. span_exporter is for tests only."""
    global ENABLED
    if ENABLED:
        return True  # one client per process; a second call must not replace its exporter
    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return False
    from langfuse import Langfuse

    Langfuse(mask_otel_spans=mask_spans, should_export_span=export_span,
             span_exporter=_redacting_exporter(span_exporter or _langfuse_otlp_exporter()))
    ENABLED = True
    return True


def traced(name: str):
    """Langfuse @observe when tracing is on, else a no-op. Decided when the function is decorated."""
    if ENABLED:
        from langfuse import observe

        return observe(name=name)
    return lambda fn: fn
