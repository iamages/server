from datetime import datetime, timezone

from pydantic import BaseModel, Field

SUPPORTED_STORAGE_VER = 4

class DatabaseVersionModel(BaseModel):
    version: int = Field(SUPPORTED_STORAGE_VER, alias="_id")
    performed_on: datetime = Field(
        ...,
        default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0)
    )
