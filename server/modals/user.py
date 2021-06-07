from datetime import datetime

from pydantic import BaseModel


class UserBase(BaseModel):
    username: str
    created: datetime

class UserInDB(UserBase):
    password: str
