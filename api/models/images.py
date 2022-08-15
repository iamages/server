from datetime import datetime
from typing import Optional

from pydantic import BaseModel, constr

from .default import DefaultModel, PyBinary


class ImageMetadata(BaseModel):
    description: constr(min_length=1, max_length=255)
    width: int
    height: int
    created_on: datetime


class Thumbnail(BaseModel):
    is_computing: bool = False
    compute_attempts: int = 0


class Image(DefaultModel):
    owner: Optional[str]
    is_private: bool
    is_locked: bool
    thumbnail: Thumbnail
    metadata: bytes


class ImageUpload(BaseModel):
    description: constr(min_length=1, max_length=255)
    is_private: bool
    is_locked: bool
    lock_key: Optional[constr(min_length=3)]
