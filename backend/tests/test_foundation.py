import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.core.database import engine
from app.core.dependencies import get_db
from app.model import Paste


def test_settings_ignore_unknown_env_keys(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "DATABASE_URL=postgresql+asyncpg://u:p@h/db\n"
        "PUBLIC_BASE_URL=http://x\n"
        "MAX_PASTE_BYTES=10\n"
        "TEST_DATABASE_URL=postgresql+asyncpg://u:p@h/db_test\n"
    )
    Settings(_env_file=env)  # raised "Extra inputs are not permitted" before extra="ignore"


def test_app_engine_logs_sql_only_in_debug():
    # echo would write every paste's text into the logs
    assert engine.echo == settings.debug


async def test_get_db_yields_a_session():
    gen = get_db()
    assert isinstance(await anext(gen), AsyncSession)
    await gen.aclose()


async def test_paste_gets_uuid_and_server_timestamp(session_maker):
    async with session_maker() as session:
        paste = Paste(text="hello")
        session.add(paste)
        await session.commit()
        await session.refresh(paste)

    assert isinstance(paste.id, uuid.UUID)
    assert paste.created_at.tzinfo is not None


async def test_paste_text_is_required(session_maker):
    async with session_maker() as session:
        session.add(Paste(text=None))
        with pytest.raises(IntegrityError):
            await session.commit()


def test_max_paste_bytes_defaults_to_1_mb(monkeypatch):
    monkeypatch.delenv("MAX_PASTE_BYTES", raising=False)
    settings = Settings(_env_file=None, database_url="postgresql+asyncpg://u:p@h/db", public_base_url="http://x")
    assert settings.max_paste_bytes == 1_048_576
