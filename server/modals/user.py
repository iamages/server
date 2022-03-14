from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UserBase(BaseModel):
    username: str
    created: datetime
    nsfw_enabled: bool
    pfp: Optional[str]

class UserInDB(UserBase):
    password: str
