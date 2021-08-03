from datetime import datetime, timezone
from distutils.util import strtobool
from enum import Enum
from os import fstat
from pathlib import Path
from shutil import copyfile
from tempfile import NamedTemporaryFile
from traceback import print_exc
from typing import Optional, Union
from uuid import UUID, uuid4

from fastapi import (APIRouter, BackgroundTasks, Depends, Form, HTTPException,
                     Request, status)
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from PIL import Image

from ..common import (FILES_PATH, THUMBS_PATH, auth_optional_dependency,
                      auth_required_dependency, compare_owner, conn, r,
                      server_config, templates)
from ..modals.file import FileBase, FileInDB
from ..modals.user import UserBase


class FileModifiableFields(str, Enum):
    description = "description"
    nsfw = "nsfw"
    private = "private"
    hidden = "hidden"

def create_thumb(img_filename: Path, mime: str):
    img_path = Path(server_config.storage_dir, "files", img_filename)
    if not img_path.exists():
        return

    thumb_path = Path(server_config.storage_dir, "thumbs", img_filename)

    with NamedTemporaryFile(suffix=img_filename.suffix) as temp:
        with Image.open(img_path) as img:
            img.thumbnail((600, 600), Image.LANCZOS)

            if mime in ["image/tiff", "image/apng", "image/gif", "image/webp"]:
                img.save(temp, save_all=True)
            else:
                img.save(temp)

        if fstat(temp.fileno()).st_size > img_path.stat().st_size:
            copyfile(img_path, thumb_path)
            return

        copyfile(temp.name, thumb_path)

def handle_str2bool(boolstr):
    if isinstance(boolstr, bool):
        return boolstr
    try:
        return bool(strtobool(boolstr))
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST)

router = APIRouter(
    prefix="/file",
    tags=["file"]
)

@router.on_event("shutdown")
def shutdown_event():
    conn.close()

@router.get(
    "/{id}/info",
    response_model=FileBase,
    description="Gets information for a file."
)
def info(
    id: UUID,
    user: Optional[UserBase] = Depends(auth_optional_dependency)
):
    file_information = r.table("files").get(str(id)).run(conn)
    if not file_information:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    file_information_parsed = FileInDB.parse_obj(file_information)
    if not file_information_parsed.private:
        file_information_parsed.owner = None
        return file_information
    
    if not compare_owner(file_information_parsed, user):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    
    return file_information

@router.get(
    "/{id}/img",
    response_class=FileResponse,
    name="img",
    description="Gets image for a file."
)
def img(
    id: UUID,
    user: Optional[UserBase] = Depends(auth_optional_dependency)
):
    file_information = r.table("files").get(str(id)).run(conn)
    if not file_information:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    file_information_parsed = FileInDB.parse_obj(file_information)

    img_path = Path(FILES_PATH, file_information_parsed.file)
    if not img_path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    if not file_information_parsed.private:
        return FileResponse(img_path, media_type=file_information_parsed.mime)

    if not compare_owner(file_information_parsed, user):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)

    return FileResponse(img_path, media_type=file_information_parsed.mime)

@router.get(
    "/{id}/thumb",
    response_class=FileResponse,
    name="thumb",
    description="Gets thumbnail for a file."
)
def thumb(
    id: UUID,
    background_tasks: BackgroundTasks,
    user: Optional[UserBase] = Depends(auth_optional_dependency)
):
    file_information = r.table("files").get(str(id)).run(conn)
    if not file_information:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    file_information_parsed = FileInDB.parse_obj(file_information)

    thumb_path = Path(THUMBS_PATH, file_information_parsed.file)

    if not thumb_path.exists():
        background_tasks.add_task(
            create_thumb,
            img_filename=file_information_parsed.file,
            mime=file_information_parsed.mime
        )
        return RedirectResponse(f"/iamages/api/v2/file/{id}/img")

    if not file_information_parsed.private:
        return FileResponse(thumb_path, media_type=file_information_parsed.mime)

    if not compare_owner(file_information_parsed, user):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)

    return FileResponse(thumb_path, media_type=file_information_parsed.mime)

@router.get(
    "/{id}/embed",
    response_class=HTMLResponse,
    name="embed",
    description="Gets embed for a file."
)
def embed(
    request: Request,
    id: UUID
):
    file_information = r.table("files").get(str(id)).run(conn)
    if not file_information:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    file_information_parsed = FileInDB(**file_information)
    if file_information_parsed.private:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)

    return templates.TemplateResponse("embed.html", {
        "request": request,
        "id": id,
        "description": file_information_parsed.description,
        "mime": file_information_parsed.mime,
        "width": file_information_parsed.width,
        "height": file_information_parsed.height,
        "created": file_information_parsed.created,
        "owner": file_information_parsed.owner or "Anonymous"
    })

@router.patch(
    "/{id}/modify",
    status_code=status.HTTP_204_NO_CONTENT,
    description="Modifies a file."
)
def modify(
    id: UUID,
    field: FileModifiableFields = Form(..., description="Data field to modify for the file."),
    data: Union[bool, str] = Form(..., min_length=1, max_length=50, description="Data given to the `field`."),
    user: UserBase = Depends(auth_required_dependency)
):
    file_information = r.table("files").get(str(id)).run(conn)
    if not file_information:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    file_information_parsed = FileInDB.parse_obj(file_information)
    if not compare_owner(file_information_parsed, user):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)

    update_query = r.table("files").get(str(id))
    
    if field == FileModifiableFields.description:
        update_query = update_query.update({
            "description": str(data)
        })
    elif field == FileModifiableFields.nsfw:
        update_query = update_query.update({
            "nsfw": handle_str2bool(data)
        })
    elif field == FileModifiableFields.private:
        update_query = update_query.update({
            "private": handle_str2bool(data)
        })
    elif field == FileModifiableFields.hidden:
        update_query = update_query.update({
            "hidden": handle_str2bool(data)
        })

    update_query.run(conn)

@router.delete(
    "/{id}/delete",
    status_code=status.HTTP_204_NO_CONTENT,
    description="Deletes a file."
)
def delete(
    id: UUID,
    user: UserBase = Depends(auth_required_dependency)
):
    file_information = r.table("files").get(str(id)).run(conn)
    if not file_information:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    file_information_parsed = FileInDB.parse_obj(file_information)
    if not compare_owner(file_information_parsed, user):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)

    img_file = Path(FILES_PATH, file_information_parsed.file)
    thumb_file = Path(THUMBS_PATH, file_information_parsed.file)
    if img_file.exists():
        img_file.unlink()
    if thumb_file.exists(): 
        thumb_file.unlink()

    r.table("files").get(str(id)).delete().run(conn)

@router.post(
    "/{id}/duplicate",
    response_model=FileBase, 
    status_code=status.HTTP_201_CREATED,
    description="Duplicates a file into an account."
)
def duplicate(
    id: UUID,
    user: UserBase = Depends(auth_required_dependency)
):
    file_information = r.table("files").get(str(id)).run(conn)
    if not file_information:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    file_information_parsed = FileInDB.parse_obj(file_information)

    if file_information_parsed.private and not compare_owner(file_information_parsed, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    duplicated_file_name = uuid4().hex + file_information_parsed.file.suffix

    duplicated_file_information = {
        "id": str(uuid4()),
    }

    duplicated_file_information = {
        "id": str(uuid4()),
        "description": file_information_parsed.description,
        "nsfw": file_information_parsed.nsfw,
        "private": True,
        "hidden": True,
        "created": datetime.now(timezone.utc).replace(microsecond=0),
        "mime": file_information_parsed.mime,
        "width": file_information_parsed.width,
        "height": file_information_parsed.height,
        "file": duplicated_file_name,
        "owner": user.username
    }

    img_file = Path(server_config.storage_dir, "files", file_information_parsed.file)
    duplicated_img_file = Path(server_config.storage_dir, "files", duplicated_file_name)
    copyfile(img_file, duplicated_img_file)

    try:
        r.table("files").insert(duplicated_file_information).run(conn)
    except:
        print_exc()
        duplicated_img_file.unlink()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR)

    return duplicated_file_information
