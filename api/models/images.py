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
    is_unavailable: bool = Field(default_factory=lambda: False)


class ImageMetadataContainer(BaseModel):
    salt: bytes | None
    nonce: bytes | None
    data: bytes | ImageMetadata
    tag: bytes | None


class LockVersion(IntEnum):
    aes128gcm_argon2 = 1


class Lock(BaseModel):
    is_locked: bool
    version: LockVersion | None
    upgradable: bool | None

    @root_validator
    def get_upgradable(cls, values) -> dict:
        if values["version"]:
            values["upgradable"] = values["version"] < LockVersion.aes128gcm_argon2
        return values


class Image(DefaultModel):
    created_on: datetime | None
    owner: str | None
    is_private: bool
    content_type: str
    lock: Lock
    thumbnail: Thumbnail | None

    @root_validator
    def get_created_on(cls, values) -> dict:
        values["created_on"] = values["id"].generation_time
        return values

class ImageInDB(Image):
    metadata: ImageMetadataContainer
    collections: list[PyObjectId] = []
    ownerless_key: UUID | None


class ImageUpload(BaseModel):
    description: constr(min_length=1, max_length=255)
    is_private: bool
    is_locked: bool
    lock_key: constr(min_length=3) | None

class EditableImageInformation(str, Enum):
    is_private = "is_private"
    lock = "lock"
    description = "description"

class ImageEditResponse(BaseModel):
    ok: bool = True
    lock_version: LockVersion | None = None
