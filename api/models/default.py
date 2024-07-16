from pydantic import BaseModel, Field, ConfigDict
from pydantic_mongo import PydanticObjectId
from typing import Optional, Annotated

class DefaultModel(BaseModel):
    id: Annotated[Optional[PydanticObjectId], Field(alias="_id")] = None

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
