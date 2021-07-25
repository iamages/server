from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, status

from ..common import (FILES_PATH, THUMBS_PATH, auth_optional_dependency,
                      auth_required_dependency, conn, pwd_context, r)
from ..modals.file import FileBase, FileInDB
from ..modals.user import UserBase, UserInDB


class UserModifiableFields(str, Enum):
    username: str = "username" 
    password: str = "password"

router = APIRouter(
    prefix="/user",
    tags=["user"]
)

@router.on_event("shutdown")
def shutdown_event():
    conn.close()

@router.get(
    "/{username}/info",
    response_model=UserBase,
    description="Gets information for an user."
)
def info(username: str):
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
    if not r.table("users").get(username).run(conn):
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    filters = r.row["owner"] == username

    if not user:
        filters = filters & (~r.row["private"]) & (~r.row["hidden"])

    if start_date:
        filters = filters & (r.row["created"] < start_date)

    query = r.table("files").filter(filters).order_by(r.desc("created"))

    if limit:
        query = query.limit(limit)

    return query.run(conn)

@router.post(
    "/{username}/files/search",
    response_model=List[FileBase],
    description="Searches through an user's files."
)
def search(
    username: str,
    user: Optional[UserBase] = Depends(auth_optional_dependency),
    description: str = Form(...),
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

    return query.run(conn)

@router.post(
    "/new",
    response_model=UserBase,
    description="Creates a new user."
)
def new(
    username: str = Form(...),
    password: str = Form(...)
):
    if len(username) <= 2 or len(password) <= 4:
        raise HTTPException(status.HTTP_400_BAD_REQUEST)

    if r.table("users").get(username).run(conn):
        raise HTTPException(status.HTTP_409_CONFLICT)

    user_information_parsed = UserInDB(
        username=username,
        password=password,
        created=datetime.now(timezone.utc)
    )

    r.table("users").insert(user_information_parsed.dict()).run(conn)

    return user_information_parsed.dict()

@router.patch(
    "/modify",
    status_code=status.HTTP_204_NO_CONTENT,
    description="Modifies an user."
)
def modify(
    field: UserModifiableFields = Form(..., description="Data field to modify for the file."),
    data: str = Form(..., description="Data given to the `field`."),
    user: UserBase = Depends(auth_required_dependency)
):
    update_query = r.table("users").get(user.username)
    
    if field == UserModifiableFields.username:
        update_query = update_query.update({
            "username": data
        })
    elif field == UserModifiableFields.password:
        update_query = update_query.update({
            "password": pwd_context.hash(data)
        })

    update_query.run(conn)
    
@router.delete(
    "/delete",
    status_code=status.HTTP_204_NO_CONTENT,
    description="Deletes an user.")
def delete(user: UserBase = Depends(auth_required_dependency)):
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
