import secrets
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Union

from fastapi import APIRouter, Body, Depends, HTTPException, status

from ..common.auth import (auth_optional_dependency, auth_required_dependency,
                           pwd_context)
from ..common.db import get_conn, r
from ..common.paths import FILES_PATH, THUMBS_PATH
from ..common.utils import handle_str2bool
from ..modals.file import FileBase, FileInDB
from ..modals.user import UserBase

def compare_user(user_db: UserBase, user_header: Optional[UserBase]):
    if user_db.private and (not user_header or not secrets.compare_digest(user_db.username, user_header.username)):
        return False
    return True

router = APIRouter(
    prefix="/user",
    tags=["user"]
)

@router.get(
    "/{username}/info",
    response_model=UserBase,
    description="Gets information for an user."
)
def info(
    username: str,
    user: Optional[UserBase] = Depends(auth_optional_dependency)
):
    with get_conn() as conn:
        user_information = r.table("users").get(username).run(conn)
    if not user_information:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    user_information_parsed = UserBase.parse_obj(user_information)
    if not compare_user(user_information_parsed, user):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)

    return user_information

@router.post(
    "/{username}/files", 
    response_model=list[FileBase],
    description="Get files owned by an user."
)
def files(
    username: str,
    user: Optional[UserBase] = Depends(auth_optional_dependency),
    limit: Optional[int] = Body(None, description="Limit file results."),
    start_date: Optional[datetime] = Body(None, description="Date to start returning results from.")
):
    with get_conn() as conn:
        user_information = r.table("users").get(username).run(conn)
        if not user_information:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        
        user_information_parsed = UserBase.parse_obj(user_information)
        if not compare_user(user_information_parsed, user):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED)

        filters = (r.row["owner"] == username)

        if not user:
            filters = filters & (~r.row["private"]) & (~r.row["hidden"])

        if start_date:
            filters = filters & (r.row["created"] < start_date)

        query = r.table("files").filter(filters).order_by(r.desc("created"))

        if limit:
            query = query.limit(limit)

        return query.run(conn)


class UserModifiableFields(str, Enum):
    private: bool = "private",
    hidden: bool = 'hidden'
    password: str = "password"

@router.patch(
    "/modify",
    status_code=status.HTTP_204_NO_CONTENT,
    description="Modifies an user."
)
def modify(
    field: UserModifiableFields = Body(..., description="Data field to modify for the file."),
    data: Union[bool, str] = Body(..., min_length=1, description="Data given to the `field`."),
    user: UserBase = Depends(auth_required_dependency)
):
    update_query = r.table("users").get(user.username)
    
    if field == UserModifiableFields.private:
        update_query = update_query.update({
            "private": handle_str2bool(data)
        })
    elif field == UserModifiableFields.hidden:
        update_query = update_query.update({
            "hidden": handle_str2bool(data)
        })
    elif field == UserModifiableFields.password:
        update_query = update_query.update({
            "password": pwd_context.hash(data)
        })

    with get_conn() as conn:
        update_query.run(conn)
    
@router.delete(
    "/delete",
    status_code=status.HTTP_204_NO_CONTENT,
    description="Deletes an user.")
def delete(user: UserBase = Depends(auth_required_dependency)):
    with get_conn() as conn:
        for file_information in r.table("files").filter(r.row["owner"] == user.username).run(conn):
            file_information_parsed = FileInDB(**file_information)
            img_file = Path(FILES_PATH, file_information_parsed.file)
            thumb_file = Path(THUMBS_PATH, file_information_parsed.file)
            if img_file.exists():
                img_file.unlink()
            if thumb_file.exists():
                thumb_file.unlink()
            r.table("files").get(str(file_information_parsed.id)).delete().run(conn)

        r.table("users").get(user.username).delete().run(conn)
