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
