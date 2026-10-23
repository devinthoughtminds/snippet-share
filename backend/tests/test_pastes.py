import json
import uuid
from datetime import datetime

import pytest

from app.core.config import settings
from app.model import Paste


async def test_create_returns_201_with_id_and_share_url(client):
    response = await client.post("/api/v1/pastes", json={"text": "hello\n  world"})

    assert response.status_code == 201
    body = response.json()
    paste_id = uuid.UUID(body["id"])
    assert body["share_url"] == f"{settings.public_base_url}/view/{paste_id}"
    datetime.fromisoformat(body["created_at"])


async def test_text_is_stored_byte_for_byte(client, session_maker):
    text = "\tindented\r\n    spaces 🎉\nlast line\n"
    response = await client.post("/api/v1/pastes", json={"text": text})

    async with session_maker() as session:
        paste = await session.get(Paste, uuid.UUID(response.json()["id"]))
    assert paste.text.encode("utf-8") == text.encode("utf-8")


@pytest.mark.parametrize(
    "payload",
    [
        {"text": ""},
        {"text": "   \n\t"},
        {},
        {"text": 123},
        {"text": "a\x00b"},  # Postgres text can't hold NUL
        {"text": "a\ud800b"},  # lone surrogate, can't be encoded as UTF-8
    ],
)
async def test_create_rejects_empty_or_invalid_text(client, payload):
    # json.dumps escapes non-ASCII (\ud800), as browsers do; httpx's json= can't send a lone surrogate.
    body = json.dumps(payload)
    response = await client.post("/api/v1/pastes", content=body, headers={"content-type": "application/json"})
    assert response.status_code == 422


async def test_create_accepts_text_of_exactly_max_bytes(client):
    response = await client.post("/api/v1/pastes", json={"text": "a" * settings.max_paste_bytes})
    assert response.status_code == 201


async def test_create_rejects_one_byte_over_max_with_413(client):
    response = await client.post("/api/v1/pastes", json={"text": "a" * (settings.max_paste_bytes + 1)})
    assert response.status_code == 413


async def test_size_limit_counts_utf8_bytes_not_characters(client):
    # 400,000 x "é" is 800,000 bytes; pad to one byte over while staying far under the limit in characters
    text = "é" * 400_000 + "a" * (settings.max_paste_bytes - 800_000 + 1)
    assert len(text) < settings.max_paste_bytes
    response = await client.post("/api/v1/pastes", json={"text": text})
    assert response.status_code == 413


async def test_get_returns_the_created_paste(client):
    created = (await client.post("/api/v1/pastes", json={"text": "hello\n  world"})).json()

    response = await client.get(f"/api/v1/pastes/{created['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert body["text"] == "hello\n  world"
    assert body["created_at"] == created["created_at"]


async def test_get_unknown_id_returns_404(client):
    response = await client.get(f"/api/v1/pastes/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.parametrize("bad_id", ["not-a-uuid", "123", "c9bf9e57-1685"])
async def test_get_malformed_id_returns_404_not_422(client, bad_id):
    response = await client.get(f"/api/v1/pastes/{bad_id}")
    assert response.status_code == 404


async def test_raw_returns_exact_text_as_plain_text(client):
    text = "\tindented\r\n    spaces 🎉\nlast line\n"
    created = (await client.post("/api/v1/pastes", json={"text": text})).json()

    response = await client.get(f"/api/v1/pastes/{created['id']}/raw")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.content == text.encode("utf-8")


@pytest.mark.parametrize("bad_id", [str(uuid.uuid4()), "not-a-uuid"])
async def test_raw_unknown_or_malformed_id_returns_404(client, bad_id):
    response = await client.get(f"/api/v1/pastes/{bad_id}/raw")
    assert response.status_code == 404


async def test_raw_never_serves_html(client):
    created = (await client.post("/api/v1/pastes", json={"text": "<script>alert(1)</script>"})).json()
    response = await client.get(f"/api/v1/pastes/{created['id']}/raw")
    assert response.headers["content-type"].startswith("text/plain")
    assert "nosniff" in response.headers.get("x-content-type-options", "")
