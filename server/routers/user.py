import secrets
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Union

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from ..common.auth import (auth_optional_dependency, auth_required_dependency,
                           pwd_context)
from ..common.db import get_conn, r
from ..common.paths import FILES_PATH, THUMBS_PATH
from ..common.templates import templates
from ..modals.collection import Collection
from ..modals.file import FileBase, FileInDB
from ..modals.user import UserBase, UserInDB


class AllUserOperation(str, Enum):
    delete_all = "delete_all"
    privatize_all = "privatize_all"
    hide_all = auto()

def compare_user(user_db: UserBase, user_header: Optional[UserBase]):
    if not user_header or not secrets.compare_digest(user_db.username, user_header.username):
        return False
    return True

def all_user_operations(username: str, operation: AllUserOperation):
    with get_conn() as conn:
        all_files = r.table("files").filter(r.row["owner"] == username).run(conn)
        all_collections = r.table("collections").filter(r.row["owner"] == username).run(conn)
        if operation == AllUserOperation.delete_all:
            for file_information in all_files:
                file_information_parsed = FileInDB.parse_obj(file_information)
                img_file = Path(FILES_PATH, file_information_parsed.file)
                thumb_file = Path(THUMBS_PATH, file_information_parsed.file)
                if img_file.exists():
                    img_file.unlink()
                if thumb_file.exists():
                    thumb_file.unlink()
                r.table("files").get(file_information_parsed.id).delete().run(conn)
            for collection_information in all_collections:
                collection_information_parsed = Collection.parse_obj(collection_information)
                r.table("collections").get(collection_information_parsed.id).delete().run(conn)
        elif operation == AllUserOperation.privatize_all:
            for file_information in all_files:
                file_information_parsed = FileInDB.parse_obj(file_information)
                r.table("files").get(file_information_parsed.id).update({
                    "private": True
                }).run(conn)
            for collection_information in all_collections:
                collection_information_parsed = Collection.parse_obj(collection_information)
                r.table("collections").get(collection_information_parsed.id).update({
                    "private": True
                }).run(conn)
        elif operation == AllUserOperation.hide_all:
            for file_information in all_files:
                file_information_parsed = FileInDB.parse_obj(file_information)
                r.table("files").get(file_information_parsed.id).update({
                    "hidden": True
                }).run(conn)
            for collection_information in all_collections:
                collection_information_parsed = Collection.parse_obj(collection_information)
                r.table("collections").get(collection_information_parsed.id).update({
                    "hidden": True
                }).run(conn)

router = APIRouter(
    prefix="/user",
    tags=["user"]
)

@router.post(
    "/new",
    response_model=UserBase,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
    description="Creates a new user."
)
def new(
    username: str = Body(..., min_length=2),
    password: str = Body(..., min_length=4)
):
    with get_conn() as conn:
        if r.table("users").get_all(username).count().eq(1).run(conn):
            raise HTTPException(status.HTTP_409_CONFLICT)

        user_information_parsed = UserInDB(
            username=username,
            private=False,
            hidden=False,
            created=datetime.now(timezone.utc),
            password=pwd_context.hash(password)
        )

        user_information = user_information_parsed.dict()

        r.table("users").insert(user_information).run(conn)

        return user_information

@router.get(
    "/check",
    status_code=status.HTTP_204_NO_CONTENT,
    description="Check credentials for an user."
)
def check(
    user: UserBase = Depends(auth_required_dependency)
):
    pass

@router.get(
    "/{username}/info",
    response_model=UserBase,
    response_model_exclude_unset=True,
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
    response_model_exclude_unset=True,
    description="Get files owned by an user."
)
def files(
    username: str,
    user: Optional[UserBase] = Depends(auth_optional_dependency),
    limit: Optional[int] = Body(None, ge=1, description="Limit file results."),
    start_date: Optional[datetime] = Body(None, description="Date to start returning results from.")
):
    with get_conn() as conn:
        user_information = r.table("users").get(username).run(conn)
        if not user_information:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        
        user_information_parsed = UserBase.parse_obj(user_information)

        filters = (r.row["owner"] == username)

        if not compare_user(user_information_parsed, user):
            filters = filters & (~r.row["private"]) & (~r.row["hidden"])

        if start_date:
            filters = filters & (r.row["created"] < start_date)

        query = r.table("files").filter(filters).order_by(r.desc("created"))

        if limit:
            query = query.limit(limit)

        return query.run(conn)

@router.post(
    "/{username}/collections",
    response_model=list[Collection],
    response_model_exclude_unset=True,
    description="Get collections owned by an user."
)
def collections(
    username: str,
    user: Optional[UserBase] = Depends(auth_optional_dependency),
    limit: Optional[int] = Body(None, ge=1, description="Limit collection results."),
    start_date: Optional[datetime] = Body(None, description="Date to start returning results from.")
):
    with get_conn() as conn:
        user_information = r.table("users").get(username).run(conn)

        if not user_information:
            raise HTTPException(status.HTTP_404_NOT_FOUND)

        user_information_parsed = UserBase.parse_obj(user_information)

        filters = (r.row["owner"] == username)

        if not compare_user(user_information_parsed, user):
            filters = filters & (~r.row["private"]) & (~r.row["hidden"])

        if start_date:
            filters = filters & (r.row["created"] < start_date)

        query = r.table("files").filter(filters).order_by(r.desc("created"))

        if limit:
            query = query.limit(limit)

        return query.run(conn)


class UserModifiableFields(str, Enum):
    password = "password"
    pfp = "pfp"

@router.patch(
    "/modify",
    status_code=status.HTTP_204_NO_CONTENT,
    description="Modifies an user."
)
def modify(
    field: UserModifiableFields = Body(..., description="Data field to modify for the file."),
    data: Union[bool, str] = Body(..., min_length=1, description="Data given to the `field`. (use `remove` if you want to remove a profile picture)"),
    user: UserBase = Depends(auth_required_dependency)
):
    with get_conn() as conn:
        update_query = r.table("users").get(user.username)

        if field == UserModifiableFields.password:
            update_query = update_query.update({
                "password": pwd_context.hash(data)
            })
        elif field == UserModifiableFields.pfp:
            if str(data) == "remove":
                update_query = update_query.update({
                    "pfp": r.literal()
                })
            else:
                file_information = r.table("files").get(str(data)).run(conn)
                if not file_information or FileBase.parse_obj(file_information).owner != user.username:
                    raise HTTPException(status.HTTP_403_FORBIDDEN)
                update_query = update_query.update({
                    "pfp": str(data)
                })

        update_query.run(conn)
    
@router.delete(
    "/delete",
    status_code=status.HTTP_202_ACCEPTED,
    description="Deletes an user.")
def delete(
    background_tasks: BackgroundTasks,
    user: UserBase = Depends(auth_required_dependency)
):
    with get_conn() as conn:
        r.table("users").get(user.username).delete().run(conn)
    background_tasks.add_task(all_user_operations, username=user.username, operation=AllUserOperation.delete_all)


class PrivatizeMethod(str, Enum):
    privatize_all = "privatize_all"
    hide_all = "hide_all"

class UserPrivatizeRequest(BaseModel):
    method: PrivatizeMethod

@router.post(
    "/privatize",
    status_code=status.HTTP_202_ACCEPTED,
    description="Mark user's files as private or hidden in bulk."
)
def privatize(
    background_tasks: BackgroundTasks,
    user: UserBase = Depends(auth_required_dependency),
    method: UserPrivatizeRequest = Body(..., description="The privatization method used.")
):
    background_tasks.add_task(all_user_operations, username=user.username, operation=method)

@router.get(
    "/{username}/pfp",
    response_class=RedirectResponse,
    name="pfp",
    description="Gets an user's profile picture."
)
def pfp(
    request: Request,
    username: str
):
    with get_conn() as conn:
        user_information = r.table("users").get(username).run(conn)
        if not user_information:
            raise HTTPException(status.HTTP_404_NOT_FOUND)

        user_information_parsed = UserBase.parse_obj(user_information)

        if not user_information_parsed.pfp or not r.table("files").get_all(user_information_parsed.pfp).count().eq(1).run(conn):
            raise HTTPException(status.HTTP_404_NOT_FOUND)
    
        return RedirectResponse(request.url_for("thumb", id=user_information_parsed.pfp) + "?analytics=0")

@router.get(
    "/{username}/embed",
    response_class=HTMLResponse,
    name="embed_user",
    description="Gets embed for an user."
)
def embed(
    request: Request,
    username: str
):
    with get_conn() as conn:
        user_information = r.table("users").get(username).run(conn)
        if not user_information:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        user_information_parsed = UserBase.parse_obj(user_information)
        if user_information_parsed.private:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED)

        return templates.TemplateResponse("embed_user.html", {
            "request": request,
            "user": user_information_parsed,
            "files": r.table("files").filter()
        })
