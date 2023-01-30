from datetime import datetime, timezone

from pydantic import BaseModel, Field

SUPPORTED_STORAGE_VER = "4.0.0"

class DatabaseVersionModel(BaseModel):
    version: str = Field(SUPPORTED_STORAGE_VER, alias="_id")
    performed_on: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0)
    )
