from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class FileBase(BaseModel):
    id: UUID
    description: str
    nsfw: bool
    private: bool
    hidden: bool
    created: datetime
    mime: str
    width: int
    height: int


class FileInDB(FileBase):
    file: Path
    owner: Optional[str]
