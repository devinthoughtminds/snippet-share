import os

from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams

from .oauth import MCP_URL, oauth_client_factory

SCANNER_URL = os.environ.get("SCANNER_URL", "http://localhost:8003/mcp")

root_agent = Agent(
    name="snippet_share_tester",
    model=os.environ.get("AGENT_MODEL", "gemini-2.5-flash"),
    instruction=(
        "You test the snippet-share MCP servers. When the user asks you to share code or text:\n"
        "1. Call scan_secrets on the exact content first.\n"
        "2. If it finds anything, do NOT share yet. List each finding (type and line) and ask whether to share "
        "the redacted version from redact_secrets, or the original. Never repeat a secret value in your reply: "
        "refer to it by type and line, and if you show the text, show only the redacted version.\n"
        "3. Call share_snippet with the content the user approved and reply with the link it returns.\n"
        "If a tool fails, show the user the exact error message."
    ),
    tools=[
        # Stateful, behind an OAuth login.
        McpToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=MCP_URL,
                timeout=120,  # covers the first connect, which waits for you to log in in the browser
                httpx_client_factory=oauth_client_factory,
            ),
        ),
        # Stateless and public: no login, no session, plain JSON answers.
        McpToolset(connection_params=StreamableHTTPConnectionParams(url=SCANNER_URL)),
    ],
)
