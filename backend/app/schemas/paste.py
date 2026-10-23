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
        # Both would otherwise surface as a 500: Postgres rejects NUL, and the size check can't encode lone surrogates.
        if "\x00" in v:
            raise ValueError("text must not contain NUL characters")
        try:
            v.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("text must be valid Unicode")
        return v  # unchanged: whitespace inside a paste is content


class PasteCreated(BaseModel):
    id: UUID
    share_url: str
    created_at: datetime


class PasteRead(BaseModel):
    id: UUID
    text: str
    created_at: datetime
