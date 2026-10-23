from sqlalchemy.ext.asyncio import AsyncSession

from app.model import Paste


async def create_paste(session: AsyncSession, text: str) -> Paste:
    paste = Paste(text=text)
    session.add(paste)
    await session.commit()
    await session.refresh(paste)  # loads the server-side created_at
    return paste
