from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CollectionBase(BaseModel):
    id: str
    description: str
    private: bool
    hidden: bool
    created: datetime

class CollectionInDB(CollectionBase):
    owner: Optional[str]
