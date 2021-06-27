from datetime import datetime, timezone
from mimetypes import guess_extension
from pathlib import Path
from tempfile import TemporaryFile
from typing import List, Optional, Tuple, IO
from urllib.request import urlopen
from uuid import uuid4

from fastapi import (APIRouter, File, Form, Header, HTTPException, Query,
                     Request, UploadFile, status)
from fastapi.responses import HTMLResponse
from PIL import Image
from pydantic import AnyHttpUrl

from ..common import conn, process_basic_auth, r, server_config, templates
from ..modals.file import FileBase


def save_img(fp: IO, path: Path, mime: str) -> Tuple[int]:
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
    tags=["everyone"]
)

@router.on_event("shutdown")
def shutdown_event():
    conn.close()

@router.get("/latest", response_model=List[FileBase])
def latest():
    return r.table("files").filter(
        (~r.row["private"]) & (~r.row["hidden"])
    ).order_by(r.desc("created")).limit(10).run(conn)

@router.get("/random", response_model=FileBase)
def random(nsfw: Optional[bool] = Query(None)):
    filters = (~r.row["private"]) & (~r.row["hidden"])
    if not nsfw:
        filters = filters & (~r.row["nsfw"])

    file_information = r.table("files").filter(filters).sample(1).run(conn)[0]

    if file_information == []:
        raise HTTPException(503)

    return file_information[0]

@router.post("/search", response_model=List[FileBase])
def search(
    description: str = Form(...),
    limit: Optional[int] = Form(None),
    start_date: Optional[datetime] = Form(None)
):
    query = r.table("files")
    filters = r.row["description"].match(f"(?i){description}") & (~r.row["private"]) & (~r.row["hidden"])

    if start_date:
        filters = filters & (r.row["created"] < start_date)

    query = query.filter(filters).order_by(r.desc("created"))

    if limit:
        query = query.limit(limit)

    return query.run(conn)

@router.post(
    "/upload",
    response_model=FileBase,
    status_code=status.HTTP_201_CREATED
)
def upload(
    description: str = Form(...),
    nsfw: bool = Form(...),
    private: Optional[bool] = Form(False),
    hidden: bool = Form(...),
    upload_file: UploadFile = File(...),
    authorization: Optional[str] = Header(None)):
    if len(description) < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST)

    if not upload_file.content_type in server_config.accept_mimes:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

    real_file_size = 0
    for chunk in upload_file.file:
        real_file_size += len(chunk)
        if real_file_size > server_config.max_size:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

    new_file_name: str = uuid4().hex + guess_extension(upload_file.content_type)
    new_file_path: Path = Path(server_config.storage_dir, "files", new_file_name)
    file_dimensions = save_img(upload_file.file, new_file_path, upload_file.content_type)

    file_information = {
        "id": str(uuid4()),
        "description": description,
        "nsfw": nsfw,
        "private": False,
        "hidden": hidden,
        "created": datetime.now(timezone.utc),
        "mime": upload_file.content_type,
        "width": file_dimensions[0],
        "height": file_dimensions[1],
        "file": new_file_name,
    }

    user_information_parsed = process_basic_auth(authorization)
    if private:
        if not user_information_parsed:
            new_file_path.unlink()
            raise HTTPException(status.HTTP_403_FORBIDDEN)
        file_information["owner"] = user_information_parsed.username
        file_information["private"] = private

    r.table("files").insert(file_information).run(conn)

    return file_information

@router.post(
    "/websave",
    response_model=FileBase,
    status_code=status.HTTP_201_CREATED
)
def websave(
    description: str = Form(...),
    nsfw: bool = Form(...),
    private: Optional[bool] = Form(False),
    hidden: bool = Form(...),
    upload_url: AnyHttpUrl = Form(...),
    authorization: Optional[str] = Header(None)):
    if len(description) <= 2:
        raise HTTPException(status.HTTP_400_BAD_REQUEST)

    new_file_name: str = ""
    new_file_path: Path = Path("")
    file_dimensions: Tuple[int] = (0, 0)
    file_mime: str = ""

    with urlopen(upload_url) as fsrc, TemporaryFile() as fdst:
        file_mime = fsrc.headers["Content-Type"]

        if not file_mime in server_config.accept_mimes:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

        real_file_size = 0
        for chunk in fsrc:
            real_file_size += len(chunk)
            if real_file_size > server_config.max_size:
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
            fdst.write(chunk)

        new_file_name = uuid4().hex + guess_extension(file_mime)
        new_file_path = Path(server_config.storage_dir, "files", new_file_name)

        file_dimensions = save_img(fdst, new_file_path, file_mime)

    file_information = {
        "id": str(uuid4()),
        "description": description,
        "nsfw": nsfw,
        "private": False,
        "hidden": hidden,
        "created": datetime.now(timezone.utc),
        "mime": file_mime,
        "width": file_dimensions[0],
        "height": file_dimensions[1],
        "file": new_file_name
    }

    user_information_parsed = process_basic_auth(authorization)
    if private:
        if not user_information_parsed:
            new_file_path.unlink()
            raise HTTPException(status.HTTP_403_FORBIDDEN)
        file_information["owner"] = user_information_parsed.username
        file_information["private"] = private

    r.table("files").insert(file_information).run(conn)

    return file_information

@router.get(
    "/private/tos",
    response_class=HTMLResponse,
    include_in_schema=False)
async def tos(request: Request):
    return templates.TemplateResponse("tos.html", {
        "request": request,
        "owner": {
            "name": server_config.server_owner,
            "contact": server_config.server_contact
        }
    })

@router.get(
    "/private/privacy",
    response_class=HTMLResponse,
    include_in_schema=False
)
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {
        "request": request,
        "owner": {
            "name": server_config.server_owner,
            "contact": server_config.server_contact
        }
    })
