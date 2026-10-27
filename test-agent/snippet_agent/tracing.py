"""Sends each conversation to Langfuse as one trace, masked with the scanner's redact(). Off unless LANGFUSE_PUBLIC_KEY is set.

ADK already puts the trace context in each MCP tool call's _meta, so the servers' spans nest under the agent's.
"""

from openinference.instrumentation.google_adk import GoogleADKInstrumentor
from snippet_tracing import init_tracing


def setup(span_exporter=None) -> bool:
    """span_exporter is for tests only."""
    on = init_tracing(span_exporter)
    if on and not GoogleADKInstrumentor().is_instrumented_by_opentelemetry:
        GoogleADKInstrumentor().instrument()
    return on
