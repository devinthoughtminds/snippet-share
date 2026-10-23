# database.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

# 1. Update the scheme to use asyncpg
DATABASE_URL = settings.database_url

# 2. Create the async engine
# echo=True logs all SQL queries to the terminal (great for development)
engine = create_async_engine(DATABASE_URL, echo=True)

# 3. Create an async session factory
async_session_maker = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)


