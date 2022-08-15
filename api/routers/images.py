from mimetypes import guess_all_extensions
from typing import IO

from anyio.to_thread import run_sync
import exif
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, Form
from fastapi.responses import StreamingResponse
from pydantic import Json

from ..common.security import get_optional_user, get_user
from ..common.db import db_images, yield_grid_file
from ..common.settings import api_settings
from ..models.default import PyObjectId
from ..models.images import Image, ImageUpload
from ..models.users import User

def check_file_size(file: IO) -> int:
    real_file_size = 0
    for chunk in file:
        real_file_size += len(chunk)
        if real_file_size > api_settings.max_size:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    file.seek(0)
    return real_file_size

router = APIRouter(prefix="/images")

@router.post(
    "/",
    response_model=Image,
    response_model_by_alias=False
)
async def upload_image(
    file: UploadFile,
    info: Json[ImageUpload] = Form(),
    user: User = Depends(get_user)
):
    file_size = run_sync(check_file_size, file=file.file)
    print(file_size)


@router.get(
    "/{id}",
    response_model=Image,
    response_model_by_alias=False
)
async def get_image_information(
    id: PyObjectId,
    user: User | None = Depends(get_optional_user)
):
    image_dict = await db_images.find_one({
        "_id": id
    })

    if not image_dict:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    image = Image.parse_obj(image_dict)

    if image.is_private and (not user or image.owner != user.username):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="You don't have permission to view this image.")

    return image
        

@router.get(
    "/{id}.{extension}",
    response_class=StreamingResponse
)
async def get_image_file(
    id: PyObjectId,
    extension: str,
    user: User | None = Depends(get_optional_user)
):
    image_dict = await db_images.find_one({
        "_id": id
    })

    if not image_dict:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    image = Image.parse_obj(image_dict)

    if image.is_private and (not user or image.owner != user.username):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="You don't have permission to view this image.")

    if not extension in guess_all_extensions(image.metadata):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Wrong image file extension.")

