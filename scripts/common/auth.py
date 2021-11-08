import secrets
from typing import Optional, Union

from fastapi import Depends, status
from fastapi.exceptions import HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from passlib.context import CryptContext

from ..modals.collection import Collection
from ..modals.file import FileInDB
from ..modals.user import UserBase, UserInDB
from .db import get_conn, r

auth_required = HTTPBasic()
auth_optional = HTTPBasic(auto_error=False)

pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    default="argon2",
    deprecated=["bcrypt"]
)

def process_basic_auth(credentials: HTTPBasicCredentials) -> Optional[UserBase]:
    with get_conn() as conn:
        user_information = r.table("users").get(credentials.username).run(conn)
    if not user_information:
        return None

    user_information_parsed = UserInDB(**user_information)
    if not (secrets.compare_digest(credentials.username, user_information_parsed.username) and pwd_context.verify(credentials.password, user_information_parsed.password)):
        return None
    
    if pwd_context.needs_update(user_information_parsed.password):
        with get_conn() as conn:
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

def compare_owner(file_or_collection_information_parsed: Optional[Union[FileInDB, Collection]], user_information_parsed: Optional[UserBase]):
    if file_or_collection_information_parsed.owner and user_information_parsed and secrets.compare_digest(file_or_collection_information_parsed.owner, user_information_parsed.username):
        return True
    return False
