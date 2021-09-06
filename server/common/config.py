from pydantic import BaseSettings, DirectoryPath
from typing import List, Optional

class ServerConfig(BaseSettings):
    iamages_max_size: int = 10485760
    iamages_accept_mimes: List[str] = ["image/jpeg", "image/png", "image/gif", "image/bmp", "image/apng", "image/webp"]
    iamages_storage_dir: DirectoryPath
    iamages_db_host: str = "localhost"
    iamages_db_port: int = 28015
    iamages_db_user: str = "iamages"
    iamages_db_pwd: str = "iamages"
    iamages_server_owner: Optional[str]
    iamages_server_contact: Optional[str]

server_config = ServerConfig()
