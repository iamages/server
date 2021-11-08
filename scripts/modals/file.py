from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class FileBase(BaseModel):
    id: str
    description: str
    nsfw: bool
    private: bool
    hidden: bool
    created: datetime
    mime: str
    width: int
    height: int
    owner: Optional[str]
    views: Optional[int]


class FileInDB(FileBase):
    file: Path
    collection: Optional[str]
