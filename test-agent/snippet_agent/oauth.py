"""The agent's side of the MCP login, using the mcp SDK's ready-made OAuth client.

OAuthClientProvider does the protocol work: it sees the 401, reads the discovery
documents, registers this agent, makes the PKCE pair, swaps the code for tokens
and refreshes them. We only supply two things it can't do itself: opening the
browser, and catching the redirect that brings the code back.
"""

import asyncio
import os
import webbrowser
from urllib.parse import parse_qs, urlparse

from google.adk.tools.mcp_tool.mcp_session_manager import create_mcp_http_client
from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import AuthorizationCodeResult, OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

MCP_URL = os.environ.get("MCP_URL", "http://localhost:8001/mcp")
CALLBACK_PORT = int(os.environ.get("OAUTH_CALLBACK_PORT", "8765"))
LOGIN_TIMEOUT = 300


class CallbackListener:
    """A one-shot local web server that waits for the browser to land on /callback?code=...&state=..."""

    def __init__(self, port: int):
        self.port = port
        self._server: asyncio.Server | None = None
        self._result: asyncio.Future[AuthorizationCodeResult] | None = None

    async def start(self) -> None:
        self._result = asyncio.get_running_loop().create_future()
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", self.port)
        self.port = self._server.sockets[0].getsockname()[1]

    async def wait(self) -> AuthorizationCodeResult:
        try:
            return await asyncio.wait_for(self._result, LOGIN_TIMEOUT)
        finally:
            self._server.close()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request_line = (await reader.readline()).decode()
        while (await reader.readline()) not in (b"\r\n", b"\n", b""):
            pass  # skip headers
        url = urlparse(request_line.split(" ")[1] if " " in request_line else "/")
        query = {k: v[0] for k, v in parse_qs(url.query).items()}

        if url.path != "/callback" or self._result.done():
            body, status = "Not found", "404 Not Found"  # e.g. the browser asking for /favicon.ico
        elif "error" in query:
            self._result.set_exception(RuntimeError(f"Login failed: {query['error']} {query.get('error_description', '')}"))
            body, status = "Login failed. You can close this tab.", "200 OK"
        else:
            self._result.set_result(AuthorizationCodeResult(code=query["code"], state=query.get("state"), iss=query.get("iss")))
            body, status = "Logged in. You can close this tab and go back to the agent.", "200 OK"

        writer.write(f"HTTP/1.1 {status}\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n{body}".encode())
        await writer.drain()
        writer.close()


class MemoryTokenStorage:
    """Where the provider keeps the agent's client registration and tokens.

    shortcut: in memory, so restarting `adk web` means logging in again; save to a file or keyring to keep the login.
    """

    def __init__(self):
        self.tokens: OAuthToken | None = None
        self.client_info: OAuthClientInformationFull | None = None

    async def get_tokens(self) -> OAuthToken | None:
        return self.tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self.tokens = tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self.client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self.client_info = client_info


_listener = CallbackListener(CALLBACK_PORT)


async def open_browser(authorization_url: str) -> None:
    await _listener.start()  # listen before the browser can come back
    print(f"\nLog in to the MCP server in your browser:\n{authorization_url}\n", flush=True)
    webbrowser.open(authorization_url)


oauth_provider = OAuthClientProvider(
    server_url=MCP_URL,
    client_metadata=OAuthClientMetadata(
        client_name="snippet-share ADK test agent",
        redirect_uris=[f"http://localhost:{CALLBACK_PORT}/callback"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",  # a public client: it can't keep a secret, which is why PKCE exists
    ),
    storage=MemoryTokenStorage(),
    redirect_handler=open_browser,
    callback_handler=_listener.wait,
)


def oauth_client_factory(headers=None, timeout=None, auth=None):
    """Plugs into ADK's McpToolset: the same HTTP client ADK would build, with our OAuth provider attached."""
    return create_mcp_http_client(headers=headers, timeout=timeout, auth=oauth_provider)
