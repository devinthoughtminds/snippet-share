"""The eval-set files are valid ADK EvalSets, and their expected arguments match what the tools really produce."""

import os
import subprocess
import sys
from pathlib import Path

from google.adk.evaluation.eval_config import EvalConfig
from google.adk.evaluation.eval_set import EvalSet
from scanner import redact

EVALS = Path(__file__).parent.parent / "evals"


def _load(name: str) -> EvalSet:
    [path] = EVALS.glob(f"*/{name}.evalset.json")
    return EvalSet.model_validate_json(path.read_text(encoding="utf-8"))


def _tool_uses(invocation):
    return [(t.name, t.args) for t in invocation.intermediate_data.tool_uses]


def test_evalsets_are_valid():
    files = sorted(EVALS.glob("*/*.evalset.json"))
    assert [f.parent.name for f in files] == ["blocks", "shares"]
    cases = [c for f in files for c in EvalSet.model_validate_json(f.read_text(encoding="utf-8")).eval_cases]
    assert sorted(c.eval_id for c in cases) == ["clean", "placeholder", "secret", "secret_then_redacted"]
    for f in files:
        EvalConfig.model_validate_json((f.parent / "test_config.json").read_text(encoding="utf-8"))


def test_redacted_share_matches_scanner_redact():
    [case] = [c for c in _load("scan_then_share").eval_cases if c.eval_id == "secret_then_redacted"]
    first, second = case.conversation
    [(name, args)] = _tool_uses(first)
    assert name == "scan_secrets"
    assert _tool_uses(second)[-1] == ("share_snippet", {"text": redact(args["text"])})


def test_secret_case_expects_only_a_scan():
    [case] = _load("secret_blocks").eval_cases
    assert [name for name, _ in _tool_uses(case.conversation[0])] == ["scan_secrets"]


def test_evals_skip_without_stack():
    env = {k: v for k, v in os.environ.items() if k != "MCP_PASSWORD"}
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/evals", "-rs", "-q", "-p", "no:cacheprovider"],
                       env=env, capture_output=True, text=True, timeout=180, cwd=EVALS.parent)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "skipped" in r.stdout and "MCP_PASSWORD" in r.stdout


def test_evals_skip_without_vertex_credentials():
    env = {**os.environ, "MCP_PASSWORD": "x", "GOOGLE_APPLICATION_CREDENTIALS": str(EVALS / "no-such-credentials.json"),
           "MCP_URL": "http://127.0.0.1:9/mcp"}
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/evals", "-rs", "-q", "-p", "no:cacheprovider"],
                       env=env, capture_output=True, text=True, timeout=180, cwd=EVALS.parent)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "skipped" in r.stdout and "gcloud auth application-default login" in r.stdout
