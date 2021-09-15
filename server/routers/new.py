from datetime import datetime, timezone
from mimetypes import guess_extension
from pathlib import Path
from tempfile import TemporaryFile
from traceback import print_exc
from typing import IO, Optional
from urllib.request import urlopen

import shortuuid
from fastapi import (APIRouter, Body, Depends, File, Form, HTTPException,
                     UploadFile, status)
from PIL import Image
from pydantic import AnyHttpUrl, BaseModel, Field, Json

from ..common.auth import auth_optional_dependency, compare_owner, pwd_context
from ..common.config import server_config
from ..common.db import get_conn, r
from ..common.paths import FILES_PATH
from ..modals.collection import CollectionBase, CollectionInDB
from ..modals.file import FileBase, FileInDB
from ..modals.user import UserBase, UserInDB


def save_img(fp: IO, path: Path, mime: str) -> tuple[int]:
    with Image.open(fp) as img:
        save_args = {
            "fp": path,
            "optimize": True,
            "quality": 100
        }

        if mime in ["image/tiff", "image/apng", "image/gif", "image/webp"]:
            save_args["save_all"] = True

        img.save(**save_args)
        return img.size

router = APIRouter(
    prefix="/new",
    tags=["new"]
)


class UploadModel(BaseModel):
    description: str
    nsfw: bool
    private: bool = Field(False, description="File privacy status. (only visible to user, requires `authorization`)")
    hidden: bool = Field(False, description="File hiding status. (visible to anyone with `id`, through links, does not show up in public lists)")

@router.post(
    "/file/upload",
    response_model=FileBase,
    status_code=status.HTTP_201_CREATED,
    description="Uploads a file from the submitted form."
)
def file_upload(
    info: Json[UploadModel] = Form(...),
    upload_file: UploadFile = File(...),
    user: Optional[UserBase] = Depends(auth_optional_dependency)
):
    if not upload_file.content_type in server_config.iamages_accept_mimes:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

    if not user and info.private:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    real_file_size = 0
    for chunk in upload_file.file:
        real_file_size += len(chunk)
        if real_file_size > server_config.iamages_max_size:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

    new_file_name = shortuuid.uuid() + guess_extension(upload_file.content_type)
    new_file_path = Path(FILES_PATH, new_file_name)
    if new_file_path.exists():
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR)
    file_dimensions = save_img(upload_file.file, new_file_path, upload_file.content_type)

    file_information_parsed = FileInDB(
        id=shortuuid.uuid(),
        description=info.description,
        nsfw=info.nsfw,
        private=False,
        hidden=info.hidden,
        created=datetime.now(timezone.utc),
        mime=upload_file.content_type,
        width=file_dimensions[0],
        height=file_dimensions[1],
        file=new_file_name
    )

    if user:
        file_information_parsed.owner = user.username
        if info.private:
            file_information_parsed.private = info.private

    file_information = file_information_parsed.dict(exclude_unset=True)
    # FIXME: Patch for 'Object of type PosixPath is not JSON serializable' in RethinkDB.
    file_information["file"] = str(file_information["file"])

    with get_conn() as conn:
        try:
            r.table("files").insert(file_information).run(conn)
        except:
            print_exc()
            new_file_path.unlink()
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR)

    return file_information


class WebSaveModel(UploadModel):
    upload_url: AnyHttpUrl

@router.post(
    "/file/websave",
    response_model=FileBase,
    status_code=status.HTTP_201_CREATED,
    description="Uploads a file from the internet."
)
def file_websave(
    info: WebSaveModel,
    user: Optional[UserBase] = Depends(auth_optional_dependency)
):
    if not user and info.private:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    new_file_name = ""
    new_file_path = Path("")
    file_dimensions = (0, 0)
    file_mime = ""

    try:
        with urlopen(info.upload_url) as fsrc, TemporaryFile() as fdst:
            file_mime = fsrc.headers["Content-Type"]

            if not file_mime in server_config.iamages_accept_mimes:
                raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

            new_file_name = shortuuid.uuid() + guess_extension(file_mime)
            new_file_path = Path(FILES_PATH, new_file_name)
            if new_file_path.exists():
                raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR)

            real_file_size = 0
            for chunk in fsrc:
                real_file_size += len(chunk)
                if real_file_size > server_config.iamages_max_size:
                    raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
                fdst.write(chunk)

            file_dimensions = save_img(fdst, new_file_path, file_mime)
    except:
        print_exc()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY)

    file_information_parsed = FileInDB(
        id=shortuuid.uuid(),
        description=info.description,
        nsfw=info.nsfw,
        private=False,
        hidden=info.hidden,
        created=datetime.now(timezone.utc),
        mime=file_mime,
        width=file_dimensions[0],
        height=file_dimensions[1],
        file=new_file_name
    )

    if user:
        file_information_parsed.owner = user.username,
        if info.private:
            file_information_parsed.private = info.private

    file_information = file_information_parsed.dict(exclude_unset=True)
    # FIXME: Patch for 'Object of type PosixPath is not JSON serializable' in RethinkDB.
    file_information["file"] = str(file_information["file"])

    with get_conn() as conn:
        try:
            r.table("files").insert(file_information).run(conn)
        except:
            print_exc()
            new_file_path.unlink()
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR)

    return file_information

@router.post(
    "/collection",
    response_model=CollectionBase,
    status_code=status.HTTP_201_CREATED,
    description="Creates a new collection."
)
def new_collection(
    description: str = Body(...),
    private: bool = Body(False, description="File privacy status. (only visible to user, requires `authorization`)"),
    hidden: bool = Body(False, description="File hiding status. (visible to anyone with `id`, through links, does not show up in public lists)"),
    file_ids: set[str] = Body(..., description="File IDs to add to collection."),
    user: Optional[UserBase] = Depends(auth_optional_dependency)
):
    if not user and private:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    with get_conn() as conn:
        for file_id in file_ids:
            file_information = r.table("files").get(file_id).run(conn)
            if not file_information:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"File ID not found: {file_id}")
            file_information_parsed = FileInDB.parse_obj(file_information)
            if file_information_parsed.private and not compare_owner(file_information_parsed, user):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=f"You don't have permission for File ID: {file_id}")
    
        collection_information_parsed = CollectionInDB(
            id=shortuuid.uuid(),
            description=description,
            private=False,
            hidden=hidden,
            created=datetime.now(timezone.utc)
        )

        if user:
            collection_information_parsed.owner = user.username
            if private:
                collection_information_parsed.private = private

        collection_information = collection_information_parsed.dict(exclude_unset=True)

        r.table("collections").insert(collection_information).run(conn)

        for file_id in file_ids:
            r.table("files").get(file_id).update({
                "collection": collection_information_parsed.id
            }).run(conn)

        return collection_information

@router.post(
    "/user",
    response_model=UserBase,
    description="Creates a new user."
)
def new_user(
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
