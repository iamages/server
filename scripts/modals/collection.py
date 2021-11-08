from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Collection(BaseModel):
    id: str
    description: str
    private: bool
    hidden: bool
    created: datetime
    owner: Optional[str]
