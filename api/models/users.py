from string import digits
from random import choice
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, constr, EmailStr


class User(BaseModel):
    username: constr(strip_whitespace=True, min_length=3) = Field(..., alias="_id")
    email: EmailStr | None
    created_on: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0))

    class Config:
        allow_population_by_field_name = True

class UserInDB(User):
    password: str

class EditableUserInformation(str, Enum):
    email = "email"
    password = "password"

class PasswordReset(BaseModel):
    email: EmailStr = Field(..., alias="_id")
    code: str = Field(default_factory=lambda: ''.join(choice(digits) for x in range(6)))
    created_on: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0))

    class Config:
        allow_population_by_field_name = True
