# snippet-share test agent

A Google ADK agent running Gemini on Vertex AI. It connects to the snippet-share MCP server the same way a real agent does: it logs in through OAuth 2.1 with PKCE, receives a JWT, and sends that JWT with every tool call.

## Setup

1. Sign in to Google Cloud once so ADK can call Vertex AI: `gcloud auth application-default login`
2. Copy `snippet_agent/.env.example` to `snippet_agent/.env` and fill in `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`.
3. `uv sync`

## Test the MCP server

You need three terminals:

```powershell
# 1. snippet-share app (repo root)
docker compose -f docker-compose.dev.yml up

# 2. MCP server
cd mcp-server; $env:MCP_PASSWORD="choose-one"; $env:MCP_JWT_SECRET="<32+ random chars>"; uv run python server.py

# 3. this agent
cd test-agent; uv run adk web
```

Open the URL `adk web` prints, pick `snippet_agent`, and ask: *"share this code: print('hi')"*.

The first time, a browser tab opens on the MCP server's login page. Type the password. The agent then receives its JWT and calls `share_snippet`, and the reply contains the link.

Tests: `uv run pytest`. The live evals in `tests/evals` skip unless `MCP_PASSWORD` is set and the stack is up.

## Traces and evals

- [snippet_agent/tracing.py](snippet_agent/tracing.py) sends each conversation to Langfuse as one trace, with the MCP servers' work nested inside, and every secret masked by the scanner's `redact()`. It's on when `LANGFUSE_PUBLIC_KEY` is set in `snippet_agent/.env`.
- [evals/](evals/) holds the eval cases. `uv run pytest tests/evals` runs them as ADK evals, and `uv run python evals/run_experiment.py` runs them as a Langfuse experiment.
- With `MCP_PASSWORD` set, the agent logs in to the MCP server with it instead of opening a browser (`password_login` in `oauth.py`), so evals run unattended.

How to start the local Langfuse, read a trace and compare experiment runs: [TESTING.md](TESTING.md#traces-and-evals).

## Where the login lives

[snippet_agent/oauth.py](snippet_agent/oauth.py) hands the `mcp` SDK's `OAuthClientProvider` to ADK through `httpx_client_factory`. The provider handles discovery, registration, PKCE, the token exchange and refreshing. This folder adds only two pieces: opening the browser, and a small local listener on port 8765 that catches the redirect.

Tokens are kept in memory, so restarting `adk web` (or the MCP server) means logging in again.
