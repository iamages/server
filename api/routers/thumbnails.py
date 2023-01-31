from os import fstat
from secrets import compare_digest
from tempfile import NamedTemporaryFile
from traceback import print_exception

from fastapi import (APIRouter, Depends, HTTPException,
                     Request, status)
from fastapi.responses import RedirectResponse, StreamingResponse
from PIL import Image as PillowImage
from PIL.Image import LANCZOS
from gridfs.errors import NoFile

from ..common.db import db_images, fs_images, fs_thumbnails, yield_grid_file
from ..common.security import get_optional_user
from ..models.default import PyObjectId
from ..models.images import ImageInDB
from ..models.users import User

def set_unavailable(id: PyObjectId):
    db_images.update_one({
        "_id": id
    }, {
        "$set": {
            "thumbnail": {
                "is_computing": False,
                "is_unavailable": True
            }
        }
    })

def create_thumbnail(id: PyObjectId):
    db_images.update_one({"_id": id}, {
        "$set": {
            "thumbnail.is_computing": True
        }
    })

    try:
        with NamedTemporaryFile() as thumbnail:
            image_grid_out = fs_images.open_download_stream(id)
            content_type = image_grid_out.metadata["content_type"]

            with PillowImage.open(image_grid_out) as image:
                image.thumbnail((512, 512), LANCZOS)
                if content_type == "image/gif":
                    image.save(thumbnail, "gif", save_all=True)
                else:
                    image.save(thumbnail, content_type.split("/")[1])

            if image_grid_out.length < fstat(thumbnail.fileno()).st_size:
                set_unavailable(id)
                return
            
            thumbnail.seek(0)
            fs_thumbnails.upload_from_stream_with_id(
                id,
                image_grid_out.filename,
                thumbnail,
                metadata={
                    "content_type": content_type
                }
            )
            db_images.update_one({"_id": id}, {
                "$set": {
                    "thumbnail.is_computing": False
                }
            })
    except Exception as e:
        set_unavailable(id)
        raise e

def stream_thumbnail(id: PyObjectId) -> StreamingResponse:
    file = fs_thumbnails.open_download_stream(id)
    return StreamingResponse(
        yield_grid_file(file),
        media_type=file.content_type, 
        headers={
            "Content-Length": str(file.length),
            "Cache-Control": f"public, max-age=86400"
        }
    )

router = APIRouter(prefix="/thumbnails")

@router.get(
    "/{id}",
    response_class=StreamingResponse,
    response_description="Thumbnail.",
    responses={
        308: {
            "description": "Thumbnail isn't available for this image."
        },
        401: {
            "description": "You don't have permission to view this thumbnail."
        },
        404: {
            "description": "Thumbnail doesn't exist."
        }
    }
)
def get_thumbnail(
    id: PyObjectId,
    request: Request,
    user: User | None = Depends(get_optional_user)
):
    image_dict = db_images.find_one({
        "_id": id
    })

    if not image_dict:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Image doesn't exist.")

    image = ImageInDB.parse_obj(image_dict)

    if image.lock.is_locked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Thumbnails are unavailable for this image.")

    if image.is_private and (not user or not compare_digest(image.owner, user.username)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="You don't have permission to view this thumbnail.")

    if image.thumbnail.is_computing:
        return RedirectResponse(request.url_for("get_image_file", id=id), headers={
             "X-Iamages-Image-Private": str(image.is_private)
        })

    try:
        return stream_thumbnail(id)
    except NoFile:
        if not image.thumbnail.is_unavailable:
            try:
                create_thumbnail(id)
                return stream_thumbnail(id)
            except Exception as e:
                print_exception(e)
                raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create thumbnail for this image.")
    except Exception as e:
        return RedirectResponse(request.url_for("get_image_file", id=id), status.HTTP_308_PERMANENT_REDIRECT, headers={
            "X-Iamages-Image-Private": str(image.is_private)
        })


