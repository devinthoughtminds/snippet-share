"""ADK evals: the real agent, the real MCP servers, Gemini on Vertex. Costs tokens and creates real pastes.

Run with the Docker stack up:  MCP_PASSWORD=<the stack's password> uv run pytest tests/evals -v -s
Skipped, with the reason, when the password, Vertex settings or the MCP server are missing.
"""

import os
from pathlib import Path

import httpx
import pytest
from dotenv import dotenv_values

AGENT_ENV = {k: v for k, v in dotenv_values(Path(__file__).parents[2] / "snippet_agent" / ".env").items() if v}
EVALS = Path(__file__).parents[2] / "evals"


def _missing() -> str:
    if not os.environ.get("MCP_PASSWORD"):
        return "set MCP_PASSWORD (the MCP login password) to run the evals"
    if not (os.environ.get("GOOGLE_CLOUD_PROJECT") or AGENT_ENV.get("GOOGLE_CLOUD_PROJECT")):
        return "set GOOGLE_CLOUD_PROJECT (or fill snippet_agent/.env) for Vertex AI"
    try:
        import google.auth
        import google.auth.transport.requests

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(google.auth.transport.requests.Request())  # catches expired sign-ins (invalid_grant) too
    except Exception as e:  # google-auth raises several types here; any of them means Vertex calls would fail
        return f"no working Google sign-in ({type(e).__name__}); run `gcloud auth application-default login`"
    mcp_url = os.environ.get("MCP_URL") or AGENT_ENV.get("MCP_URL", "http://localhost:8001/mcp")
    base = mcp_url.rsplit("/mcp", 1)[0]
    try:
        httpx.get(f"{base}/.well-known/oauth-authorization-server", timeout=2).raise_for_status()
    except httpx.HTTPError as e:
        return f"MCP server not reachable at {base} ({type(e).__name__}); start the Docker stack"
    return ""


_REASON = _missing()
pytestmark = pytest.mark.skipif(bool(_REASON), reason=_REASON or "ready")


@pytest.mark.parametrize("path", sorted(EVALS.glob("*/*.evalset.json")), ids=lambda p: p.parent.name)
async def test_agent_eval(path):
    for k, v in AGENT_ENV.items():
        os.environ.setdefault(k, v)  # the same settings adk web loads, before the agent is imported

    from google.adk.evaluation.agent_evaluator import AgentEvaluator

    try:
        # Each file's test_config.json sits next to it. A directory would only pick up *.test.json files.
        await AgentEvaluator.evaluate(agent_module="snippet_agent", eval_dataset_file_path_or_dir=str(path), num_runs=1)
    finally:
        import snippet_tracing

        if snippet_tracing.ENABLED:
            from langfuse import get_client

            get_client().flush()  # short runs must not lose their spans
