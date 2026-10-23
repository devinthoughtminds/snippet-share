import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_db
from app.model import Paste
from app.schemas.paste import PasteCreate, PasteCreated, PasteRead
from app.services import paste as paste_service

router = APIRouter(prefix="/api/v1/pastes", tags=["pastes"])


async def get_paste_or_404(paste_id: str, session: AsyncSession) -> Paste:
    # A malformed id is just a paste that doesn't exist: 404, not 422.
    try:
        parsed = uuid.UUID(paste_id)
    except ValueError:
        raise HTTPException(404, "Paste not found")
    paste = await paste_service.get_paste(session, parsed)
    if paste is None:
        raise HTTPException(404, "Paste not found")
    return paste


@router.post("", status_code=201, response_model=PasteCreated)
async def create_paste(body: PasteCreate, session: AsyncSession = Depends(get_db)):
    # Here, not in the schema: a validator can only produce 422. Measure bytes, not characters.
    try:
        size = len(body.text.encode("utf-8"))
    except UnicodeEncodeError:
        # Lone surrogate. Not a validator error: FastAPI's 422 body echoes the input and can't encode it either.
        raise HTTPException(422, "text must be valid Unicode")
    if size > settings.max_paste_bytes:
        raise HTTPException(413, "Paste exceeds 1 MB")
    paste = await paste_service.create_paste(session, body.text)
    return PasteCreated(
        id=paste.id,
        share_url=f"{settings.public_base_url.rstrip('/')}/view/{paste.id}",
        created_at=paste.created_at,
    )


# paste_id is a str on purpose, so FastAPI doesn't answer malformed ids with its own 422.
@router.get("/{paste_id}", response_model=PasteRead)
async def read_paste(paste_id: str, session: AsyncSession = Depends(get_db)):
    paste = await get_paste_or_404(paste_id, session)
    return PasteRead(id=paste.id, text=paste.text, created_at=paste.created_at)
