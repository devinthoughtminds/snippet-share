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
