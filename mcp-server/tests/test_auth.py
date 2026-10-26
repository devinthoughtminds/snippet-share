import base64
import hashlib
import re
import secrets
import time
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest

import server

BASE = "http://localhost:8001"
REDIRECT = "http://localhost:9999/callback"
INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


SECRET = "test-signing-secret-at-least-32-bytes!"


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setattr(server, "PASSWORD", "letmein")
    monkeypatch.setattr(server.provider, "jwt_secret", SECRET)


# Not a fixture: the app's lifespan must start and stop in the same task, which async fixtures don't guarantee.
@asynccontextmanager
async def mcp_client():
    app = server.mcp.streamable_http_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as c:
            yield c


async def start_login(client):
    """Register a client and start /authorize with PKCE, like Claude Code does. Returns what the next steps need."""
    reg = await client.post("/register", json={"redirect_uris": [REDIRECT], "token_endpoint_auth_method": "none"})
    assert reg.status_code == 201, reg.text
    client_id = reg.json()["client_id"]

    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    auth = await client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "xyz",
            "resource": f"{BASE}/mcp",
        },
    )
    assert auth.status_code == 302, auth.text
    login_url = auth.headers["location"]
    assert login_url.startswith(f"{BASE}/login?req=")
    page = await client.get(login_url)
    req = re.search(r'name="req" value="([^"]+)"', page.text).group(1)
    return client_id, verifier, req


async def log_in(client):
    """Run the whole browser part and return (client_id, verifier, code)."""
    client_id, verifier, req = await start_login(client)
    login = await client.post("/login", data={"req": req, "password": "letmein"})
    assert login.status_code == 302
    return client_id, verifier, login.headers["location"]


async def get_token(client, client_id, verifier, code):
    return await client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT,
            "client_id": client_id,
            "code_verifier": verifier,
            "resource": f"{BASE}/mcp",
        },
    )


async def test_mcp_without_token_points_to_metadata():
    async with mcp_client() as client:
        resp = await client.post("/mcp", json=INIT, headers=MCP_HEADERS)
        assert resp.status_code == 401
        assert "/.well-known/oauth-protected-resource/mcp" in resp.headers["www-authenticate"]

        meta = await client.get("/.well-known/oauth-protected-resource/mcp")
        assert meta.json()["authorization_servers"] == [BASE]


async def test_full_login_flow_gives_working_token():
    async with mcp_client() as client:
        client_id, verifier, location = await log_in(client)
        callback = urlparse(location)
        query = parse_qs(callback.query)
        assert f"{callback.scheme}://{callback.netloc}{callback.path}" == REDIRECT
        assert query["state"] == ["xyz"]

        token = await get_token(client, client_id, verifier, query["code"][0])
        assert token.status_code == 200, token.text
        access = token.json()["access_token"]

        resp = await client.post("/mcp", json=INIT, headers={**MCP_HEADERS, "Authorization": f"Bearer {access}"})
        assert resp.status_code == 200, resp.text

        # A code works once: replaying it must fail.
        replay = await get_token(client, client_id, verifier, query["code"][0])
        assert replay.status_code == 400


async def test_wrong_password_gives_no_code():
    async with mcp_client() as client:
        _, _, req = await start_login(client)

        login = await client.post("/login", data={"req": req, "password": "nope"})
        assert login.status_code == 401
        assert "location" not in login.headers


async def test_made_up_token_is_rejected():
    async with mcp_client() as client:
        resp = await client.post("/mcp", json=INIT, headers={**MCP_HEADERS, "Authorization": "Bearer made-up"})
        assert resp.status_code == 401


async def test_access_token_is_signed_jwt():
    async with mcp_client() as client:
        client_id, verifier, location = await log_in(client)
        code = parse_qs(urlparse(location).query)["code"][0]
        access = (await get_token(client, client_id, verifier, code)).json()["access_token"]

        claims = jwt.decode(access, SECRET, algorithms=["HS256"], audience=f"{BASE}/mcp", issuer=BASE)
        assert claims["client_id"] == client_id
        assert claims["exp"] - claims["iat"] == 3600


async def test_forged_jwt_is_rejected():
    forged = jwt.encode(
        {"iss": BASE, "aud": f"{BASE}/mcp", "sub": "me", "client_id": "x", "exp": time.time() + 600},
        "some-other-secret-at-least-32-bytes!",
        algorithm="HS256",
    )
    async with mcp_client() as client:
        resp = await client.post("/mcp", json=INIT, headers={**MCP_HEADERS, "Authorization": f"Bearer {forged}"})
        assert resp.status_code == 401


async def test_refresh_rotates_tokens():
    async with mcp_client() as client:
        client_id, verifier, location = await log_in(client)
        code = parse_qs(urlparse(location).query)["code"][0]
        first = (await get_token(client, client_id, verifier, code)).json()

        refresh = {"grant_type": "refresh_token", "refresh_token": first["refresh_token"], "client_id": client_id}
        refreshed = await client.post("/token", data=refresh)
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()["access_token"] != first["access_token"]

        # The old refresh token is spent.
        again = await client.post("/token", data=refresh)
        assert again.status_code == 400
