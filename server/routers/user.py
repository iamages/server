import secrets
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Union

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status, BackgroundTasks, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from ..common.auth import (auth_optional_dependency, auth_required_dependency,
                           pwd_context)
from ..common.db import db_conn_mgr, r
from ..common.paths import FILES_PATH, THUMBS_PATH
from ..common.templates import templates
from ..modals.collection import Collection
from ..modals.file import FileBase, FileInDB
from ..modals.user import UserBase, UserInDB
from ..common.config import server_config


class AllUserOperation(str, Enum):
    delete_all = "delete_all"
    privatize_all = "privatize_all"
    hide_all = auto()

def compare_user(user_db: UserBase, user_header: Optional[UserBase]):
    if not user_header or not secrets.compare_digest(user_db.username, user_header.username):
        return False
    return True

async def all_user_operations(username: str, operation: AllUserOperation):
    all_files = await r.table("files").filter(r.row["owner"] == username).run(db_conn_mgr.conn)
    all_collections = await r.table("collections").filter(r.row["owner"] == username).run(db_conn_mgr.conn)
    if operation == AllUserOperation.delete_all:
        for file_information in all_files:
            file_information_parsed = FileInDB.parse_obj(file_information)
            img_file = Path(FILES_PATH, file_information_parsed.file)
            thumb_file = Path(THUMBS_PATH, file_information_parsed.file)
            if img_file.exists():
                img_file.unlink()
            if thumb_file.exists():
                thumb_file.unlink()
            await r.table("files").get(file_information_parsed.id).delete().run(db_conn_mgr.conn)
        for collection_information in all_collections:
            collection_information_parsed = Collection.parse_obj(collection_information)
            await r.table("collections").get(collection_information_parsed.id).delete().run(db_conn_mgr.conn)
    elif operation == AllUserOperation.privatize_all:
        for file_information in all_files:
            file_information_parsed = FileInDB.parse_obj(file_information)
            await r.table("files").get(file_information_parsed.id).update({
                "private": True
            }).run(db_conn_mgr.conn)
        for collection_information in all_collections:
            collection_information_parsed = Collection.parse_obj(collection_information)
            await r.table("collections").get(collection_information_parsed.id).update({
                "private": True
            }).run(db_conn_mgr.conn)
    elif operation == AllUserOperation.hide_all:
        for file_information in all_files:
            file_information_parsed = FileInDB.parse_obj(file_information)
            await r.table("files").get(file_information_parsed.id).update({
                "hidden": True
            }).run(db_conn_mgr.conn)
        for collection_information in all_collections:
            collection_information_parsed = Collection.parse_obj(collection_information)
            await r.table("collections").get(collection_information_parsed.id).update({
                "hidden": True
            }).run(db_conn_mgr.conn)

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
async def new(
    username: str = Body(..., min_length=2),
    password: str = Body(..., min_length=4)
):
    if await r.table("users").get_all(username).count().eq(1).run(db_conn_mgr.conn):
        raise HTTPException(status.HTTP_409_CONFLICT)

    user_information_parsed = UserInDB(
        username=username,
        private=False,
        hidden=False,
        nsfw_enabled=False,
        created=datetime.now(timezone.utc),
        password=pwd_context.hash(password)
    )

    user_information = user_information_parsed.dict()

    await r.table("users").insert(user_information).run(db_conn_mgr.conn)

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
async def info(
    username: str,
    user: Optional[UserBase] = Depends(auth_optional_dependency)
):
    user_information = await r.table("users").get(username).run(db_conn_mgr.conn)
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
async def files(
    username: str,
    nsfw: bool = Query(False),
    user: Optional[UserBase] = Depends(auth_optional_dependency),
    limit: Optional[int] = Body(None, ge=1, description="Limit file results."),
    start_date: Optional[datetime] = Body(None, description="Date to start returning results from.")
):
    user_information = await r.table("users").get(username).run(db_conn_mgr.conn)
    if not user_information:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    
    user_information_parsed = UserBase.parse_obj(user_information)

    filters = (r.row["owner"] == username)

    if not compare_user(user_information_parsed, user):
        filters = filters & (~r.row["private"]) & (~r.row["hidden"])

    if not nsfw:
        filters = filters & (~r.row["nsfw"])

    if start_date:
        filters = filters & (r.row["created"] < start_date)

    query = r.table("files").filter(filters).order_by(r.desc("created"))

    if limit:
        query = query.limit(limit)

    return await query.run(db_conn_mgr.conn)

@router.post(
    "/{username}/collections",
    response_model=list[Collection],
    response_model_exclude_unset=True,
    description="Get collections owned by an user."
)
async def collections(
    username: str,
    user: Optional[UserBase] = Depends(auth_optional_dependency),
    limit: Optional[int] = Body(None, ge=1, description="Limit collection results."),
    start_date: Optional[datetime] = Body(None, description="Date to start returning results from.")
):
    user_information = await r.table("users").get(username).run(db_conn_mgr.conn)

    if not user_information:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    user_information_parsed = UserBase.parse_obj(user_information)

    filters = (r.row["owner"] == username)

    if not compare_user(user_information_parsed, user):
        filters = filters & (~r.row["private"]) & (~r.row["hidden"])

    if start_date:
        filters = filters & (r.row["created"] < start_date)

    query = r.table("collections").filter(filters).order_by(r.desc("created"))

    if limit:
        query = query.limit(limit)

    return await query.run(db_conn_mgr.conn)


class UserModifiableFields(str, Enum):
    password = "password"
    pfp = "pfp"

@router.patch(
    "/modify",
    status_code=status.HTTP_204_NO_CONTENT,
    description="Modifies an user."
)
async def modify(
    field: UserModifiableFields = Body(..., description="Data field to modify for the file."),
    data: Union[bool, str] = Body(..., min_length=1, description="Data given to the `field`. (use `remove` if you want to remove a profile picture)"),
    user: UserBase = Depends(auth_required_dependency)
):
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
            file_information = await r.table("files").get(str(data)).run(db_conn_mgr.conn)
            if not file_information or FileBase.parse_obj(file_information).owner != user.username:
                raise HTTPException(status.HTTP_403_FORBIDDEN)
            update_query = update_query.update({
                "pfp": str(data)
            })

    await update_query.run(db_conn_mgr.conn)
    
@router.delete(
    "/delete",
    status_code=status.HTTP_202_ACCEPTED,
    description="Deletes an user.")
async def delete(
    background_tasks: BackgroundTasks,
    user: UserBase = Depends(auth_required_dependency)
):
    await r.table("users").get(user.username).delete().run(db_conn_mgr)
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
async def pfp(
    request: Request,
    username: str
):
    user_information = await r.table("users").get(username).run(db_conn_mgr.conn)
    if not user_information:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    user_information_parsed = UserBase.parse_obj(user_information)

    if not user_information_parsed.pfp or not await r.table("files").get_all(user_information_parsed.pfp).count().eq(1).run(db_conn_mgr.conn):
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    return RedirectResponse(request.url_for("thumb", id=user_information_parsed.pfp) + "?analytics=0")

@router.get(
    "/{username}/embed",
    response_class=HTMLResponse,
    name="embed_user",
    description="Gets embed for an user."
)
async def embed(
    request: Request,
    username: str
):
    user_information = await r.table("users").get(username).run(db_conn_mgr.conn)
    if not user_information:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    user_information_parsed = UserBase.parse_obj(user_information)

    return templates.TemplateResponse("embed_user.html", {
        "request": request,
        "user": user_information_parsed,
        "files": r.table("files").filter((r.row["owner"] == username) & ~r.row["private"] & ~r.row["hidden"]).order_by(r.desc("created")).limit(10).run(conn)
    })

@router.get(
    "/nsfw_toggle",
    response_class=HTMLResponse,
    name="nsfw_toggle",
    include_in_schema=False
)
async def nsfw_toggle(
    request: Request
):
    return templates.TemplateResponse("nsfw_toggle.html", {
        "request": request
    })

@router.post(
    "/nsfw_toggled",
    response_class=HTMLResponse,
    name="nsfw_toggled",
    include_in_schema=False
)
async def nsfw_toggled(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    toggled = False
    user = None
    try:
        user = UserInDB.parse_obj(await r.table("users").get(username).run(db_conn_mgr.conn))
        if pwd_context.verify(password, user.password):
            await r.table("users").get(username).update({
                "nsfw_enabled": not user.nsfw_enabled
            }).run(db_conn_mgr.conn)
            toggled = True
    except:
        pass
    return templates.TemplateResponse("nsfw_toggled.html", {
        "request": request,
        "toggled": toggled,
        "status": (not user.nsfw_enabled) if user else None,
        "owner": {
            "contact": server_config.iamages_server_contact
        }
    })
