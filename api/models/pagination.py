from typing import Annotated

from pydantic import BaseModel, Field
from pydantic_mongo import PydanticObjectId


class Pagination(BaseModel):
    query: str | None = None
    last_id: PydanticObjectId | None = None
    limit: Annotated[int, Field(ge=1, le=15)]  = 3