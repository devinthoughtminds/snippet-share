"""Remote MCP server: lets Claude Code / Codex turn text into a snippet-share link, behind an OAuth 2.1 login."""

import hmac
import html
import os

import httpx
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from auth import InMemoryAuthProvider

API_URL = os.environ.get("SNIPPET_API_URL", "http://localhost:8000").rstrip("/")
PUBLIC_URL = os.environ.get("MCP_PUBLIC_URL", "http://localhost:8001").rstrip("/")
RESOURCE_URL = f"{PUBLIC_URL}/mcp"
PASSWORD = os.environ.get("MCP_PASSWORD", "")
JWT_SECRET = os.environ.get("MCP_JWT_SECRET", "")

provider = InMemoryAuthProvider(PUBLIC_URL, RESOURCE_URL, JWT_SECRET)

mcp = MCPServer(
    "snippet-share",
    auth_server_provider=provider,
    auth=AuthSettings(
        issuer_url=PUBLIC_URL,  # who hands out tokens: this same app
        resource_server_url=RESOURCE_URL,  # what the tokens are for: the /mcp endpoint
        validate_token_resource=True,  # refuse tokens issued for any other server
        client_registration_options=ClientRegistrationOptions(enabled=True),
        revocation_options=RevocationOptions(enabled=True),
    ),
)


# The agent sees the name, type hints and docstring below; they are how it decides to call this tool.
@mcp.tool()
async def share_snippet(text: str) -> str:
    """Save text (code, docs, a chat excerpt) to snippet-share and return a shareable link.

    Use when the user asks for a link to share something you wrote. Pass the exact content, max 1 MB.
    """
    # Raise ToolError, not other exceptions: the SDK hides any other error's message from the agent.
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{API_URL}/api/v1/pastes", json={"text": text}, timeout=10)
    except httpx.HTTPError as e:
        raise ToolError(f"Could not reach snippet-share at {API_URL}. Is the app running? ({e})")
    if resp.status_code != 201:
        detail = resp.json().get("detail", resp.text) if resp.headers.get("content-type") == "application/json" else resp.text
        raise ToolError(f"snippet-share rejected the snippet ({resp.status_code}): {detail}")
    return resp.json()["share_url"]


def login_page(req: str, error: str = "", status: int = 200) -> HTMLResponse:
    message = f"<p style='color:#b00'>{error}</p>" if error else ""
    return HTMLResponse(
        f"""<!doctype html><meta name="viewport" content="width=device-width">
<title>snippet-share login</title>
<form method="post" action="/login" style="max-width:20rem;margin:4rem auto;font-family:sans-serif">
  <h1>snippet-share</h1>
  <p>An agent wants to share snippets for you.</p>{message}
  <input type="hidden" name="req" value="{html.escape(req)}">
  <label>Password <input type="password" name="password" autofocus required></label>
  <button>Allow</button>
</form>""",
        status_code=status,
    )


# Custom routes skip the bearer check: the login page is how you get a token in the first place.
@mcp.custom_route("/login", methods=["GET"])
async def show_login(request: Request) -> Response:
    req = request.query_params.get("req", "")
    if not provider.is_pending(req):
        return HTMLResponse("This login link expired. Ask the agent to connect again.", status_code=400)
    return login_page(req)


@mcp.custom_route("/login", methods=["POST"])
async def submit_login(request: Request) -> Response:
    form = await request.form()
    req, password = str(form.get("req", "")), str(form.get("password", ""))
    if not provider.is_pending(req):
        return HTMLResponse("This login link expired. Ask the agent to connect again.", status_code=400)
    # compare_digest: constant time, so response timing doesn't leak how much of the password matched.
    # Wrong guesses are rate limited by nginx (docker-compose); run behind it, or add a limit here.
    if not PASSWORD or not hmac.compare_digest(password.encode(), PASSWORD.encode()):
        return login_page(req, "Wrong password.", status=401)
    return RedirectResponse(provider.approve(req), status_code=302)


if __name__ == "__main__":
    if not PASSWORD:
        raise SystemExit("Set MCP_PASSWORD to the password people type on the login page.")
    if len(JWT_SECRET) < 32:
        raise SystemExit('Set MCP_JWT_SECRET to 32+ random characters (python -c "import secrets; print(secrets.token_urlsafe(32))").')
    # shortcut: binds to localhost only; set MCP_HOST=0.0.0.0 (and configure transport security) when deploying.
    mcp.run("streamable-http", host=os.environ.get("MCP_HOST", "127.0.0.1"), port=int(os.environ.get("MCP_PORT", "8001")))
