from pydantic import BaseSettings, DirectoryPath

class ServerConfig(BaseSettings):
    iamages_storage_dir: DirectoryPath
    iamages_db_host: str = "localhost"
    iamages_db_port: int = 28015
    iamages_db_user: str = "iamages"
    iamages_db_pwd: str = "iamages"

server_config = ServerConfig()

