from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UserBase(BaseModel):
    username: str
    private: bool
    hidden: bool
    created: datetime
    pfp: Optional[str]

class UserInDB(UserBase):
    password: str
