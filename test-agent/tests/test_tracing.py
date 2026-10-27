import os
import subprocess
import sys

from openinference.instrumentation.google_adk import GoogleADKInstrumentor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


def test_setup_off_without_keys():
    env = {k: v for k, v in os.environ.items() if not k.startswith("LANGFUSE_")}
    r = subprocess.run([sys.executable, "-c", "from snippet_agent import tracing; print(tracing.setup())"],
                       env=env, capture_output=True, text=True, timeout=120)
    assert r.stdout.strip() == "False", r.stderr
    assert r.stderr == ""


def test_setup_instruments_adk(monkeypatch):
    from snippet_agent import tracing

    for k, v in {"LANGFUSE_PUBLIC_KEY": "pk-lf-test", "LANGFUSE_SECRET_KEY": "sk-lf-test", "LANGFUSE_BASE_URL": "http://127.0.0.1:9"}.items():
        monkeypatch.setenv(k, v)
    assert tracing.setup(InMemorySpanExporter()) is True
    assert GoogleADKInstrumentor().is_instrumented_by_opentelemetry
    assert tracing.setup() is True  # a second call is safe
