from datetime import datetime
from typing import Optional

from bson.binary import Binary
from pydantic import BaseModel

from .default import DefaultModel


class CollectionMetadata(BaseModel):
    description: str
    created: datetime

class Collection(DefaultModel):
    owner: Optional[str]
    is_private: bool
    metadata: Binary
