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


@pytest.mark.parametrize("payload", [{"text": ""}, {"text": "   \n\t"}, {}, {"text": 123}])
async def test_create_rejects_empty_or_invalid_text(client, payload):
    response = await client.post("/api/v1/pastes", json=payload)
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
