from datetime import datetime
from enum import Enum, IntEnum
from uuid import UUID

from pydantic import BaseModel, Field, constr, root_validator

from .default import DefaultModel, PyObjectId


class ImageMetadata(BaseModel):
    description: constr(min_length=1, max_length=255)
    width: int
    height: int
    real_content_type: str | None


class Thumbnail(BaseModel):
    is_computing: bool = Field(default_factory=lambda: False)
    is_unavailable: bool = Field(default_factory=lambda: True)


class Metadata(BaseModel):
    salt: bytes | None
    nonce: bytes | None
    data: bytes
    tag: bytes | None


class LockVersion(IntEnum):
    aes128gcm_argon2 = 1


class Lock(BaseModel):
    is_locked: bool
    version: LockVersion | None
    upgradable: bool | None


class Image(DefaultModel):
    created_on: datetime | None
    owner: str | None
    is_private: bool
    content_type: str
    lock: Lock
    thumbnail: Thumbnail | None
    collection: PyObjectId | None

    @root_validator
    def get_created_on(cls, values) -> dict:
        values["created_on"] = values["id"].generation_time
        return values

class ImageInDB(Image):
    metadata: Metadata
    ownerless_key: UUID | None


class ImageUpload(BaseModel):
    description: constr(min_length=1, max_length=255)
    is_private: bool
    is_locked: bool
    lock_key: constr(min_length=3) | None


class ImageInformationType(str, Enum):
    public = "public"
    private = "private"

class EditableImageInformation(str, Enum):
    is_private = "is_private"
    lock = "lock"
    description = "description"

class ImageEditResponse(BaseModel):
    ok: bool = True
    lock_version: LockVersion | None = None
