import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

# The Langfuse client is a per-process singleton, so every tracing test shares one in-memory exporter.
_EXPORTER = InMemorySpanExporter()
FAKE_KEYS = {"LANGFUSE_PUBLIC_KEY": "pk-lf-test", "LANGFUSE_SECRET_KEY": "sk-lf-test", "LANGFUSE_BASE_URL": "http://127.0.0.1:9"}


@pytest.fixture
def exporter(monkeypatch):
    import snippet_tracing

    for k, v in FAKE_KEYS.items():
        monkeypatch.setenv(k, v)
    snippet_tracing.init_tracing(_EXPORTER)
    _EXPORTER.clear()
    yield _EXPORTER
    _EXPORTER.clear()
