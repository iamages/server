from pydantic import BaseSettings

class APISettings(BaseSettings):
    max_size: int = 10485760
    db_url: str
    jwt_secret: str
    server_owner: str | None
    server_contact: str | None

    class Config:
        env_prefix = "iamages_"

api_settings = APISettings()
