from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, status

from ..common.auth import (auth_optional_dependency, auth_required_dependency,
                           pwd_context)
from ..common.db import get_conn, r
from ..common.paths import FILES_PATH, THUMBS_PATH
from ..modals.file import FileBase, FileInDB
from ..modals.user import UserBase, UserInDB


class UserModifiableFields(str, Enum):
    password: str = "password"

def check_user_exists(username: str):
    with get_conn() as conn:
        return r.table("users").get_all(username).count().eq(1).run(conn)

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
    username: str
):
    with get_conn() as conn:
        user_information = r.table("users").get(username).run(conn)
    if not user_information:
        raise HTTPException(404)

    return user_information

@router.post(
    "/{username}/files", 
    response_model=List[FileBase],
    description="Get files owned by an user."
)
def files(
    username: str,
    user: Optional[UserBase] = Depends(auth_optional_dependency),
    limit: Optional[int] = Form(None, description="Limit file results."),
    start_date: Optional[datetime] = Form(None, description="Date to start returning results from.")
):
    if not check_user_exists(username):
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    filters = r.row["owner"] == username

    if not user:
        filters = filters & (~r.row["private"]) & (~r.row["hidden"])

    if start_date:
        filters = filters & (r.row["created"] < start_date)

    query = r.table("files").filter(filters).order_by(r.desc("created"))

    if limit:
        query = query.limit(limit)

    with get_conn() as conn:
        return query.run(conn)

@router.post(
    "/{username}/files/search",
    response_model=List[FileBase],
    description="Searches through an user's files."
)
def search(
    username: str,
    user: Optional[UserBase] = Depends(auth_optional_dependency),
    description: str = Form(..., min_length=1),
    limit: Optional[int] = Form(None, description="Limit search results."),
    start_date: Optional[datetime] = Form(None, description="Date to start searching from.")
):
    query = r.table("files")
    filters = (r.row["owner"] == username) & (r.row["description"].match(f"(?i){description}"))

    if not user:
        filters = filters & (~r.row["private"]) & (~r.row["hidden"])

    if start_date:
        filters = filters & (r.row["created"] < start_date)

    query = query.filter(filters).order_by(r.desc("created"))

    if limit:
        query = query.limit(limit)

    with get_conn() as conn:
        return query.run(conn)

@router.post(
    "/new",
    response_model=UserBase,
    description="Creates a new user."
)
def new(
    username: str = Form(..., min_length=1),
    password: str = Form(..., min_length=1)
):
    if len(username) <= 2 or len(password) <= 4:
        raise HTTPException(status.HTTP_400_BAD_REQUEST)

    if check_user_exists(username):
        raise HTTPException(status.HTTP_409_CONFLICT)

    user_information_parsed = UserInDB(
        username=username,
        password=pwd_context.hash(password),
        created=datetime.now(timezone.utc)
    )

    with get_conn() as conn:
        r.table("users").insert(user_information_parsed.dict()).run(conn)

    return user_information_parsed.dict()

@router.patch(
    "/modify",
    status_code=status.HTTP_204_NO_CONTENT,
    description="Modifies an user."
)
def modify(
    field: UserModifiableFields = Form(..., description="Data field to modify for the file."),
    data: str = Form(..., min_length=1, description="Data given to the `field`."),
    user: UserBase = Depends(auth_required_dependency)
):
    update_query = r.table("users").get(user.username)
    
    if field == UserModifiableFields.password:
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
