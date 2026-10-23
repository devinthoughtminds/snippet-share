import uuid
from datetime import datetime

from app.core.config import settings


async def test_create_returns_201_with_id_and_share_url(client):
    response = await client.post("/api/v1/pastes", json={"text": "hello\n  world"})

    assert response.status_code == 201
    body = response.json()
    paste_id = uuid.UUID(body["id"])
    assert body["share_url"] == f"{settings.public_base_url}/view/{paste_id}"
    datetime.fromisoformat(body["created_at"])
