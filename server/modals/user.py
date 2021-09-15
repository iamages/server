from datetime import datetime

from pydantic import BaseModel


class UserBase(BaseModel):
    username: str
    private: bool
    hidden: bool
    created: datetime

class UserInDB(UserBase):
    password: str
