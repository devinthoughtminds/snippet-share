"""Stateless MCP server: finds and redacts secrets in text before an agent shares it.

Stateless means each POST /mcp is handled on its own: the server issues no Mcp-Session-Id and
remembers nothing between requests. Any copy of it can answer any request, and a restart loses
nothing. The price: no channel back to the agent between requests (no progress updates, sampling
or elicitation), which these one-shot tools don't need.
"""

import os

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel

from scanner import redact, scan
from snippet_tracing import init_tracing, traced

init_tracing()  # before the tools below are decorated; a no-op unless LANGFUSE_PUBLIC_KEY is set

mcp = MCPServer(
    "secret-scanner",
    instructions="Check text for leaked secrets before sharing it publicly. "
    "Call scan_secrets first; if it finds anything, offer redact_secrets' output instead of the original.",
)


class Finding(BaseModel):
    type: str
    line: int
    preview: str  # masked: never the secret itself


class ScanResult(BaseModel):
    found: int
    findings: list[Finding]


# Returning a model gives the agent structured JSON (structuredContent) plus an output schema in tools/list.
@mcp.tool()
@traced("scan_secrets")
def scan_secrets(text: str) -> ScanResult:
    """Find API keys, tokens, passwords and private keys in text. Returns each finding's type, line and a masked preview.

    Call this before sharing any code, config or log publicly. It never returns the secret values.
    """
    findings = scan(text)
    return ScanResult(found=len(findings), findings=[Finding(**f) for f in findings])


@mcp.tool()
@traced("redact_secrets")
def redact_secrets(text: str) -> str:
    """Return the text with every secret scan_secrets would find replaced by [REDACTED:<type>]. Everything else is kept exactly."""
    return redact(text)


def streamable_app():
    # The two lines that make it stateless:
    #   stateless_http: a fresh transport per request, no session id, no handshake required first.
    #   json_response:  answer with one plain JSON body instead of an event stream (nothing to stream anyway).
    return mcp.streamable_http_app(
        stateless_http=True, json_response=True, host=os.environ.get("MCP_HOST", "127.0.0.1")
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(streamable_app(), host=os.environ.get("MCP_HOST", "127.0.0.1"), port=int(os.environ.get("MCP_PORT", "8003")))
