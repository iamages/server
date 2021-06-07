import binascii
import secrets
from base64 import b64decode
from pathlib import Path
from typing import List, Optional

from fastapi.security.utils import get_authorization_scheme_param
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
    storage_ver: int = SUPPORTED_STORAGE_VER
    db_host: str = "localhost"
    db_port: int = 28015
    db_user: str = "iamages"
    db_pwd: str = "iamages"
    server_owner: Optional[str]
    server_contact: Optional[str]

Image.MAX_IMAGE_PIXELS = None

server_config = ServerConfig()

r = RethinkDB()
conn = r.connect(
    host=server_config.db_host,
    port=server_config.db_port,
    user=server_config.db_user,
    password=server_config.db_pwd,
    db="iamages"
)
if r.table("internal").order_by(r.desc("created")).sample(1).run(conn)[0]["version"] != server_config.storage_ver:
    exit(1)

templates = Jinja2Templates(directory=Path("./server/web/templates"))

pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    default="argon2",
    deprecated=["bcrypt"]
)

def process_basic_auth(authorization: Optional[str]) -> Optional[UserBase]:
    if not authorization:
        return None

    scheme, credentials = get_authorization_scheme_param(authorization)

    if scheme.lower() != "basic" or not credentials:
        return None
    
    try:
        credentials_decoded = b64decode(credentials).decode('utf-8')
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return None

    username, separator, password = credentials_decoded.partition(":")
    if not separator:
        return None

    user_information = r.table("users").get(username).run(conn)
    if not user_information:
        return None

    user_information_parsed = UserInDB(**user_information)
    if not (secrets.compare_digest(username, user_information_parsed.username) and pwd_context.verify(password, user_information_parsed.password)):
        return None
    
    if pwd_context.needs_update(user_information_parsed.password):
        r.table("users").get(user_information_parsed.username).update({
            "password": pwd_context.hash(password)
        }).run(conn)
    return UserBase(**user_information)

def compare_owner(file_information_parsed: Optional[FileInDB], user_information_parsed: Optional[UserInDB]):
    if file_information_parsed.owner and user_information_parsed and secrets.compare_digest(file_information_parsed.owner, user_information_parsed.username):
        return True

    return False
