from pydantic import BaseModel, conint

from .default import PyObjectId

class Pagination(BaseModel):
    query: str | None
    last_id: PyObjectId | None
    limit: conint(ge=1, le=15) = 3