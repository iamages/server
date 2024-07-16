from enum import Enum
from typing import Annotated
from datetime import datetime

from pydantic import BaseModel, StringConstraints, computed_field
from pydantic_mongo import PydanticObjectId

from .default import DefaultModel

class Collection(DefaultModel):
    @computed_field
    @property
    def created_on(self) -> datetime | None:
        if not self.id:
            return None
        return self.id.generation_time
    owner: str | None = None
    is_private: bool
    description: Annotated[str, StringConstraints(min_length=1, max_length=255)] 


class NewCollection(BaseModel):
    is_private: bool
    description: Annotated[str, StringConstraints(min_length=1, max_length=255)] 
    image_ids: list[PydanticObjectId] = []

class EditableCollectionInformation(str, Enum):
    description = "description"
    is_private = "is_private"
    add_images = "add_images"
    remove_images = "remove_images"