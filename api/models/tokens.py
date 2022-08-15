from datetime import datetime

from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class JWTModal(BaseModel):
    sub: str
    exp: datetime
