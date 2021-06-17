from pydantic import BaseSettings, DirectoryPath


class ServerConfig(BaseSettings):
    storage_dir: DirectoryPath
    db_host: str = "localhost"
    db_port: int = 28015
    db_user: str = "iamages"
    db_pwd: str = "iamages"

server_config = ServerConfig()
