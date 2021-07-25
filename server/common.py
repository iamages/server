import secrets
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, status
from fastapi.exceptions import HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from PIL import Image
from pydantic import BaseSettings, DirectoryPath
from rethinkdb import RethinkDB

from .modals.file import FileInDB
from .modals.user import UserBase, UserInDB

SUPPORTED_STORAGE_VER = 3


class ServerConfig(BaseSettings):
    max_size: int = 10485760
    accept_mimes: List[str] = ["image/jpeg", "image/png", "image/gif", "image/bmp", "image/apng", "image/webp"]
    storage_dir: DirectoryPath
    db_host: str = "localhost"
    db_port: int = 28015
    db_user: str = "iamages"
    db_pwd: str = "iamages"
    server_owner: Optional[str]
    server_contact: Optional[str]

Image.MAX_IMAGE_PIXELS = None

server_config = ServerConfig()

FILES_PATH = Path(server_config.storage_dir, "files")
THUMBS_PATH = Path(server_config.storage_dir, "thumbs")

r = RethinkDB()
conn = r.connect(
    host=server_config.db_host,
    port=server_config.db_port,
    user=server_config.db_user,
    password=server_config.db_pwd,
    db="iamages"
)
if r.table("internal").order_by(r.desc("created")).sample(1).run(conn)[0]["version"] != SUPPORTED_STORAGE_VER:
    exit(1)

templates = Jinja2Templates(directory=Path("./server/web/templates"))

auth_required = HTTPBasic()
auth_optional = HTTPBasic(auto_error=False)

pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    default="argon2",
    deprecated=["bcrypt"]
)

def process_basic_auth(credentials: HTTPBasicCredentials) -> Optional[UserBase]:
    user_information = r.table("users").get(credentials.username).run(conn)
    if not user_information:
        return None

    user_information_parsed = UserInDB(**user_information)
    if not (secrets.compare_digest(credentials.username, user_information_parsed.username) and pwd_context.verify(credentials.password, user_information_parsed.password)):
        return None
    
    if pwd_context.needs_update(user_information_parsed.password):
        r.table("users").get(user_information_parsed.username).update({
            "password": pwd_context.hash(credentials.password)
        }).run(conn)

    return UserBase(**user_information)

def auth_required_dependency(credentials: HTTPBasicCredentials = Depends(auth_required)) -> UserBase:
    user = process_basic_auth(credentials)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    return user

def auth_optional_dependency(credentials: Optional[HTTPBasicCredentials] = Depends(auth_optional)) -> Optional[UserBase]:
    if credentials:
        return process_basic_auth(credentials)

def compare_owner(file_information_parsed: Optional[FileInDB], user_information_parsed: Optional[UserBase]):
    if file_information_parsed.owner and user_information_parsed and secrets.compare_digest(file_information_parsed.owner, user_information_parsed.username):
        return True
    return False
