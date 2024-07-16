from pydantic import EmailStr, DirectoryPath, Field
from pydantic_settings import BaseSettings

class APISettings(BaseSettings):
    max_size: int = 30000000 # 30MB
    db_url: str
    storage_dir: DirectoryPath
    jwt_secret: str
    server_owner: str
    server_contact: str
    smtp_host: str
    smtp_port: int
    smtp_starttls: bool
    smtp_username: str | None = Field(None)
    smtp_password: str | None = Field(None)
    smtp_from: EmailStr

    class Config:
        env_prefix = "iamages_"

api_settings = APISettings()
