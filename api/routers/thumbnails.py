from secrets import compare_digest
from shutil import copyfileobj
from tempfile import SpooledTemporaryFile
from traceback import print_exception

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from PIL import Image as PillowImage
from PIL.Image import LANCZOS

from ..common.db import db_images
from ..common.paths import IMAGES_PATH, THUMBNAILS_PATH
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

def create_thumbnail(image: ImageInDB):
    db_images.update_one({"_id": image.id}, {
        "$set": {
            "thumbnail.is_computing": True
        }
    })

    try:
        file_name = f"{image.id}{image.file.type_extension}"
        with SpooledTemporaryFile() as temporary:
            image_file_path = IMAGES_PATH / file_name

            pil_image = PillowImage.open(image_file_path)
            pil_image.thumbnail((512, 512), LANCZOS)
            pil_image.save(temporary, pil_image.format, save_all=getattr(pil_image, "is_animated", False))
            pil_image.close()

            if image_file_path.stat().st_size < temporary.tell():
                set_unavailable(image.id)
                return False

            temporary.seek(0)

            with open(THUMBNAILS_PATH / file_name, "wb") as thumbnail_file:
                copyfileobj(temporary, thumbnail_file)

        db_images.update_one({"_id": image.id}, {
            "$set": {
                "thumbnail.is_computing": False
            }
        })
        return True
    except Exception as e:
        set_unavailable(image.id)
        raise e

def return_file_response(image: ImageInDB) -> FileResponse:
    file_name = f"{image.id}{image.file.type_extension}"
    path = THUMBNAILS_PATH / file_name
    if not path.exists():
        raise FileNotFoundError()
    return FileResponse(
        path,
        filename=file_name,
        media_type=image.file.content_type,
        headers={
            "Cache-Control": "public, max-age=86400"
        }
    )

def return_redirect_response(image: ImageInDB, request: Request) -> RedirectResponse:
    return RedirectResponse(
        request.url_for("get_image_file", id=image.id, extension=image.file.type_extension.lstrip(".")),
        status.HTTP_308_PERMANENT_REDIRECT,
        headers={
            "X-Iamages-Image-Private": str(image.is_private)
        }
    )

router = APIRouter(prefix="/thumbnails")

@router.get(
    "/{id}.{extension}",
    response_class=FileResponse,
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
    extension: str,
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

    if image.file.type_extension.lstrip(".") != extension:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Wrong file extension.")

    if image.thumbnail.is_computing:
        return RedirectResponse(request.url_for("get_image_file", id=id, extension=extension), headers={
             "X-Iamages-Image-Private": str(image.is_private)
        })

    try:
        return return_file_response(image)
    except FileNotFoundError:
        if not image.thumbnail.is_unavailable:
            try:
                if not create_thumbnail(image):
                    return return_redirect_response(image, request)
                return return_file_response(image)
            except Exception as e:
                print_exception(e)
                raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create thumbnail for this image.")
        else:
            return return_redirect_response(image, request)
    except Exception as e:
        print_exception(e)
        return return_redirect_response(image, request)


