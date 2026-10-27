import asyncio

import httpx
import pytest

from snippet_agent.oauth import CallbackListener, oauth_client_factory, oauth_provider


async def test_listener_returns_code_and_state():
    listener = CallbackListener(port=0)  # 0: any free port
    await listener.start()

    async with httpx.AsyncClient() as browser:
        resp = await browser.get(f"http://127.0.0.1:{listener.port}/callback", params={"code": "abc", "state": "xyz"})
    result = await listener.wait()

    assert resp.status_code == 200
    assert (result.code, result.state) == ("abc", "xyz")


async def test_listener_reports_denied_login():
    listener = CallbackListener(port=0)
    await listener.start()

    async with httpx.AsyncClient() as browser:
        await browser.get(f"http://127.0.0.1:{listener.port}/callback", params={"error": "access_denied"})

    with pytest.raises(RuntimeError, match="access_denied"):
        await listener.wait()


async def test_listener_ignores_other_paths():
    listener = CallbackListener(port=0)
    await listener.start()

    async with httpx.AsyncClient() as browser:
        await browser.get(f"http://127.0.0.1:{listener.port}/favicon.ico")
        await browser.get(f"http://127.0.0.1:{listener.port}/callback", params={"code": "abc", "state": "s"})

    assert (await asyncio.wait_for(listener.wait(), 5)).code == "abc"


def test_factory_attaches_oauth():
    client = oauth_client_factory(headers={"X-Test": "1"})
    assert client.auth is oauth_provider
    assert client.headers["X-Test"] == "1"


def _fake_mcp(monkeypatch, login_status, login_location="/login?req=r1", callback="code=c1&state=s1&iss=http://mcp"):
    # Stands in for the MCP server: /authorize sends you to /login, /login checks the password.
    import functools

    from snippet_agent import oauth

    seen = {}

    def handler(request):
        if request.url.path == "/authorize":
            return httpx.Response(302, headers={"Location": login_location})
        seen["form"] = dict(httpx.QueryParams(request.content.decode()))
        if login_status != 302:
            return httpx.Response(login_status, text="Wrong password")
        return httpx.Response(302, headers={"Location": f"http://localhost:8765/callback?{callback}"})

    monkeypatch.setattr(oauth.httpx, "AsyncClient", functools.partial(httpx.AsyncClient, transport=httpx.MockTransport(handler)))
    monkeypatch.setenv("MCP_PASSWORD", "pw")
    monkeypatch.setattr(oauth, "MCP_URL", "http://mcp/mcp")
    return seen


async def test_password_login_returns_code(monkeypatch):
    from snippet_agent.oauth import _password_result, password_login

    seen = _fake_mcp(monkeypatch, 302)
    await password_login("http://mcp/authorize?client_id=x&state=s1")
    result = await _password_result()

    assert seen["form"] == {"req": "r1", "password": "pw"}
    assert (result.code, result.state, result.iss) == ("c1", "s1", "http://mcp")


async def test_password_login_wrong_password(monkeypatch):
    from snippet_agent.oauth import password_login

    _fake_mcp(monkeypatch, 401)
    with pytest.raises(RuntimeError, match="401"):
        await password_login("http://mcp/authorize?client_id=x&state=s1")


def test_provider_logs_in_headlessly_when_password_is_set():
    import os
    import subprocess
    import sys

    code = "from snippet_agent import oauth; print(oauth.oauth_provider.context.redirect_handler is oauth.password_login)"
    env = {**{k: v for k, v in os.environ.items() if not k.startswith("LANGFUSE_")}, "MCP_PASSWORD": "pw"}
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120)
    assert r.stdout.strip() == "True", r.stderr


async def test_password_login_refuses_another_origin(monkeypatch):
    from snippet_agent.oauth import password_login

    seen = _fake_mcp(monkeypatch, 302, login_location="http://elsewhere/login?req=r1")
    with pytest.raises(RuntimeError, match="elsewhere"):
        await password_login("http://mcp/authorize?client_id=x&state=s1")
    assert "form" not in seen  # the password was never sent


async def test_password_login_reports_denied_login(monkeypatch):
    from snippet_agent.oauth import password_login

    _fake_mcp(monkeypatch, 302, callback="error=access_denied&state=s1")
    with pytest.raises(RuntimeError, match="access_denied"):
        await password_login("http://mcp/authorize?client_id=x&state=s1")
