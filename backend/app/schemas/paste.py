from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator


class PasteCreate(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def text_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be empty")
        if "\x00" in v:  # Postgres text can't store NUL; it would be a 500
            raise ValueError("text must not contain NUL characters")
        return v  # unchanged: whitespace inside a paste is content


class PasteCreated(BaseModel):
    id: UUID
    share_url: str
    created_at: datetime


class PasteRead(BaseModel):
    id: UUID
    text: str
    created_at: datetime
