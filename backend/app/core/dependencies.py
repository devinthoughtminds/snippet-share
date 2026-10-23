# dependencies.py (or directly in database.py)
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import async_session_maker

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides an async database session."""
    async with async_session_maker() as session:
        yield session
