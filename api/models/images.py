from enum import Enum, IntEnum
from uuid import UUID
from typing import Annotated
from datetime import datetime

from pydantic import BaseModel, computed_field, StringConstraints
from pydantic_mongo import PydanticObjectId

from .default import DefaultModel

class ImageMetadata(BaseModel):
    description: Annotated[str, StringConstraints(min_length=1, max_length=255)] 
    width: int
    height: int
    real_content_type: str | None = None


class File(BaseModel):
    content_type: str
    type_extension: str
    salt: bytes | None = None
    nonce: bytes | None = None
    tag: bytes | None = None


class Thumbnail(BaseModel):
    is_computing: bool = False
    is_unavailable: bool = False


class ImageMetadataContainer(BaseModel):
    salt: bytes | None = None
    nonce: bytes | None = None
    data: bytes | ImageMetadata
    tag: bytes | None = None


class LockVersion(IntEnum):
    aes128gcm_argon2 = 1


class Lock(BaseModel):
    is_locked: bool
    version: LockVersion | None = None

    @computed_field
    @property
    def upgradable(self) -> bool | None:
        if self.version:
            return self.version < LockVersion.aes128gcm_argon2


class Image(DefaultModel):
    @computed_field
    @property
    def created_on(self) -> datetime | None:
        if not self.id:
            return None
        return self.id.generation_time
    owner: str | None = None
    is_private: bool
    lock: Lock
    file: File
    thumbnail: Thumbnail | None = None
    metadata: ImageMetadataContainer

class ImageInDB(Image):
    collections: list[PydanticObjectId] = []
    ownerless_key: UUID | None = None

class ImageUpload(BaseModel):
    description: Annotated[str, StringConstraints(min_length=1, max_length=255)] 
    is_private: bool
    is_locked: bool
    lock_key: Annotated[str, StringConstraints(min_length=3)] | None

class EditableImageInformation(str, Enum):
    is_private = "is_private"
    lock = "lock"
    description = "description"

class ImageEditResponse(BaseModel):
    ok: bool = True
    lock_version: LockVersion | None = None
    file: File | None = None
    metadata_salt: bytes | None = None
