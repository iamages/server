from pydantic import BaseSettings
from typing import Optional

class APISettings(BaseSettings):
    max_size: int = 10485760
    db_url: str
    jwt_secret: str
    server_owner: Optional[str]
    server_contact: Optional[str]

    class Config:
        env_prefix = "iamages_"

api_settings = APISettings()
