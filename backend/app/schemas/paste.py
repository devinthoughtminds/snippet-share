from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PasteCreate(BaseModel):
    text: str


class PasteCreated(BaseModel):
    id: UUID
    share_url: str
    created_at: datetime
