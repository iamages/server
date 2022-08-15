from datetime import datetime, timezone

from pydantic import BaseModel, Field, constr


class User(BaseModel):
    username: constr(strip_whitespace=True, min_length=3) = Field(..., alias="_id")
    created: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0))

    class Config:
        allow_population_by_field_name = True

class UserInDB(User):
    password: constr(min_length=3)
