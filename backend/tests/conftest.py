import os

import pytest
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

load_dotenv()  # backend/.env; real env vars (Docker, CI) take precedence

from app.core.dependencies import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.model import Base  # noqa: E402

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
# Tests drop and truncate tables, so only ever point them at a *_test database.
if not TEST_DATABASE_URL or not (make_url(TEST_DATABASE_URL).database or "").endswith("_test"):
    raise pytest.UsageError("TEST_DATABASE_URL must point at a *_test database (see backend/.env.example)")


@pytest.fixture(scope="session")
async def engine():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        # Rebuild so the test schema always matches the models (create_all never alters).
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_db(engine):
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE pastes"))


@pytest.fixture
def session_maker(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def client(session_maker):
    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
