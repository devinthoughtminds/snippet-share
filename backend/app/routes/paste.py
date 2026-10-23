from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_db
from app.schemas.paste import PasteCreate, PasteCreated
from app.services import paste as paste_service

router = APIRouter(prefix="/api/v1/pastes", tags=["pastes"])


@router.post("", status_code=201, response_model=PasteCreated)
async def create_paste(body: PasteCreate, session: AsyncSession = Depends(get_db)):
    paste = await paste_service.create_paste(session, body.text)
    return PasteCreated(
        id=paste.id,
        share_url=f"{settings.public_base_url.rstrip('/')}/view/{paste.id}",
        created_at=paste.created_at,
    )
