from mimetypes import guess_extension
from os import fstat
from secrets import compare_digest
from tempfile import NamedTemporaryFile

import bson
import cv2
from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException,
                     Request, status)
from fastapi.responses import RedirectResponse, StreamingResponse

from ..common.security import get_optional_user
from ..common.db import db_images, fs_images, fs_thumbnails, yield_grid_file
from ..models.default import PyObjectId
from ..models.images import Image, ImageMetadata
from ..models.users import User


async def create_thumbnail(id: PyObjectId, content_type: str):
    await db_images.update_one({
        "_id": id
    }, {
        "$set": {
            "thumbnail.is_computing": True
        }
    })

    with (
        NamedTemporaryFile() as original,
        NamedTemporaryFile() as thumbnail
    ):
        await fs_images.download_to_stream(id, original)

        if content_type == "image/gif":
            cap = cv2.VideoCapture(original.name)
            ret, image = cap.read()
            if ret:
                thumb = cv2.resize(image, (600, 600))
                cv2.imwrite(thumbnail.name, thumb)
            cap.release()
            
        else:
            image = cv2.imread(original.name)
            thumb = cv2.resize(image, (600, 600))
            cv2.imwrite(thumbnail.name, thumb)

        if fstat(original.fileno()).st_size > fstat(thumbnail.fileno()).st_size:
            await db_images.update_one({
                "_id": id
            }, {
                "$set": {
                    "thumbnail.is_computing": False
                },
                "$inc": {
                    "thumbnail.compute_attempts": 1
                }
            })
        else:
            await fs_thumbnails.upload_from_stream_with_id(
                id,
                f"{id}{guess_extension(content_type)}",
                thumbnail,
                metadata={
                    "contentType": content_type
                }
            )

router = APIRouter(prefix="/thumbnails")

@router.get(
    "/{id}.{extension}",
    response_class=StreamingResponse,
    response_description="Thumbnail.",
    responses={
        307: {
            "description": "Thumbnail isn't ready yet."
        },
        401: {
            "description": "You don't have permission to view this thumbnail."
        },
        403: {
            "description": "Thumbnails are unavailable for this image."
        },
        404: {
            "description": "Thumbnail doesn't exist."
        }
    }
)
async def get_thumbnail(
    id: PyObjectId,
    extension: str,
    background_tasks: BackgroundTasks,
    request: Request,
    user: User | None = Depends(get_optional_user)
):
    image_dict = await db_images.find_one({
        "_id": id
    })

    if not image_dict:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Image doesn't exist.")

    image = Image.parse_obj(image_dict)

    if image.is_locked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Thumbnails are unavailable for this image.")

    if image.is_private and not compare_digest(image.owner, user.username):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="You don't have permission to view this thumbnail.")

    image_metadata = ImageMetadata.parse_obj(bson.decode(image.metadata))

    if not image.thumbnail.is_computing and image.thumbnail.compute_attempts >= 1:
        background_tasks.add_task(create_thumbnail, id=id, content_type=image_metadata.content_type)
        return RedirectResponse(request.get_url("image", id=id, extension=extension))

    file = await fs_thumbnails.open_download_stream(id)
    return StreamingResponse(yield_grid_file(file), media_type=file.content_type, headers={
        "Content-Length": file.length
    })

