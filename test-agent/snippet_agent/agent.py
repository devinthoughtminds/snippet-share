import os

from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams

from .oauth import MCP_URL, oauth_client_factory

root_agent = Agent(
    name="snippet_share_tester",
    model=os.environ.get("AGENT_MODEL", "gemini-2.5-flash"),
    instruction=(
        "You test the snippet-share MCP server. When the user asks you to share code or text, "
        "call share_snippet with the exact content and reply with the link it returns. "
        "If the tool fails, show the user the exact error message."
    ),
    tools=[
        McpToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=MCP_URL,
                timeout=120,  # covers the first connect, which waits for you to log in in the browser
                httpx_client_factory=oauth_client_factory,
            ),
        )
    ],
)
