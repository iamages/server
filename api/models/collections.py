from datetime import datetime
from typing import Optional
from enum import Enum

from pydantic import BaseModel, root_validator, constr

from .default import DefaultModel, PyObjectId


class CollectionMetadata(BaseModel):
    description: constr(min_length=1, max_length=255)

class Collection(DefaultModel):
    created_on: Optional[datetime]
    owner: Optional[str]
    is_private: bool
    metadata: CollectionMetadata

    @root_validator
    def get_created_date(cls, values) -> dict:
        values["created_on"] = values["id"].generation_time
        return values

class NewCollection(BaseModel):
    is_private: bool
    description: constr(min_length=1, max_length=255)
    image_ids: list[PyObjectId] = []

class EditableCollectionInformation(str, Enum):
    description = "description"
    is_private = "is_private"
    add_images = "add_images"
    remove_images = "remove_images"