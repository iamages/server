from base64 import b64decode, b64encode
from mimetypes import guess_extension
from secrets import compare_digest
from shutil import copyfileobj
from tempfile import SpooledTemporaryFile
from typing import BinaryIO
from uuid import UUID, uuid4

import magic
import orjson
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from fastapi import (APIRouter, Body, Depends, Form, Header, HTTPException,
                     Request, UploadFile, status)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, HTMLResponse, Response
from passlib.hash import argon2
from PIL import Image as PillowImage
from PIL.ImageOps import exif_transpose
from pydantic import Json
from pydantic.json import ENCODERS_BY_TYPE

from ..common.db import db_images
from ..common.paths import IMAGES_PATH, THUMBNAILS_PATH
from ..common.security import get_optional_user, get_user
from ..common.settings import api_settings
from ..common.templates import templates
from ..models.default import PyObjectId
from ..models.images import (EditableImageInformation, File, Image,
                             ImageEditResponse, ImageInDB, ImageMetadata,
                             ImageMetadataContainer, ImageUpload, Lock,
                             LockVersion, Thumbnail)
from ..models.users import User

ENCODERS_BY_TYPE[bytes] = lambda b: b64encode(b).decode("utf-8")

SUPPORTED_MIME_TYPES = [
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp"
]

def check_file_size(file: BinaryIO) -> int:
    real_file_size = 0
    for chunk in file:
        real_file_size += len(chunk)
        if real_file_size > api_settings.max_size:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    file.seek(0)
    return real_file_size

def hash_password(key: str, salt: bytes = None) -> tuple[bytes, bytes]:
    # Follow recommended rfc9106 parameters.
    hasher = argon2.using(
        salt=salt,
        salt_len=16 if not salt else None, 
        hash_len=16,
        time_cost=3,
        memory_cost=65536,
        parallelism=4
    )
    hashed_key = hasher.hash(key).split("$")
    # Incorrect padding fix.
    return (b64decode(hashed_key[-1] + "=="), b64decode(hashed_key[-2] + "=="))

def get_image_in_db(id: PyObjectId, user: User | None) -> ImageInDB:
    image_dict = db_images.find_one({
        "_id": id
    })

    if not image_dict:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    image = ImageInDB.parse_obj(image_dict)

    if image.is_private and (not user or image.owner != user.username):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="You don't have permission to view this image.")

    return image

def check_key_len(key: str) -> bytes:
    key_bytes = b64decode(key)
    if len(key_bytes) != 16:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Metadata lock key is not exactly 16 bytes.")
    return key_bytes

router = APIRouter(prefix="/images")

@router.post(
    "/",
    response_model=Image,
    response_model_exclude={
        "file": {
            "salt": ...,
            "nonce": ...,
            "tag": ...
        },
        "metadata": ...
    },
    response_model_by_alias=False,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED
)
def upload_image(
    file: UploadFile,
    response: Response,
    information: Json[ImageUpload] = Form(),
    user: User | None = Depends(get_optional_user)
):
    if information.is_locked and not information.lock_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Lock key not set for locked image.")

    if information.is_private and not user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="You cannot set file to private without being logged in.")
        
    
    size = check_file_size(file.file)

    mime = magic.from_buffer(file.file.read(2048 if size >= 2048 else size), mime=True)
    if mime != file.content_type:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="File MIME type doesn't match what's given in the request.")
    if not mime in SUPPORTED_MIME_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="We only accept JPEG, PNG, GIF and WebP formats.")

    file.file.seek(0)

    original_pil_image = PillowImage.open(file.file)
    # Correct orientation
    transposed_pil_image = exif_transpose(original_pil_image)
    width, height = transposed_pil_image.size
    transposed_pil_image.format = original_pil_image.format
    original_pil_image.close()

    image_metadata = ImageMetadata(
        description=information.description,
        width=width,
        height=height,
        real_content_type=mime if information.is_locked else None
    )

    image_metadata_bytes = None
    nonce = None
    tag = None
    key = None
    salt = None

    if information.is_locked:
        image_metadata_bytes = orjson.dumps(image_metadata.dict(exclude_none=True))
        key, salt = hash_password(information.lock_key)

        nonce = get_random_bytes(12)

        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)

        image_metadata_bytes, tag = cipher.encrypt_and_digest(image_metadata_bytes)

    image = ImageInDB(
        is_private=information.is_private,
        lock=Lock(
            is_locked=information.is_locked,
            version=LockVersion.aes128gcm_argon2 if information.is_locked else None
        ),
        file=File(
            content_type="application/octet-stream" if information.is_locked else mime,
            type_extension=guess_extension("application/octet-stream") if information.is_locked else guess_extension(mime)
        ),
        metadata=ImageMetadataContainer(
            salt=salt,
            nonce=nonce,
            data=image_metadata_bytes if information.is_locked else image_metadata,
            tag=tag,
        )
    )
    if user:
        image.owner = user.username
    else:
        ownerless_key = uuid4()
        image.ownerless_key = ownerless_key
        response.headers["X-Iamages-Ownerless-Key"] = str(ownerless_key)
    if not information.is_locked:
        image.thumbnail = Thumbnail()

    with SpooledTemporaryFile() as temporary:
        transposed_pil_image.save(temporary, format=transposed_pil_image.format, save_all=getattr(transposed_pil_image, "is_animated", False))
        transposed_pil_image.close()

        if information.is_locked:
            key, salt = hash_password(information.lock_key)
            image.file.salt = salt

            nonce = get_random_bytes(12)
            image.file.nonce = nonce

            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)

            encrypted_image_bytes, tag = cipher.encrypt_and_digest(temporary.read())
            temporary.seek(0)
            temporary.write(encrypted_image_bytes)

            image.file.tag = tag

        temporary.seek(0)

        with open(IMAGES_PATH / f"{image.id}{image.file.type_extension}", "wb") as image_file:
            copyfileobj(temporary, image_file)

    db_images.insert_one(
        image.dict(by_alias=True, exclude_none=True, exclude={
            "created_on": ...,
            "lock": {"upgradable": ...}
        })
    )

    return image.dict()

@router.api_route(
    "/{id}.{extension}",
    methods=["GET", "HEAD"],
    response_class=FileResponse
)
def get_image_file(
    id: PyObjectId,
    extension: str,
    user: User | None = Depends(get_optional_user)
):
    image = get_image_in_db(id, user)

    if image.file.type_extension.lstrip(".") != extension:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Wrong file extension.")

    headers = {
        "Cache-Control": "public, max-age=86400"
    }

    if image.lock.is_locked:
        headers["X-Iamages-Lock-Salt"] = b64encode(image.file.salt).decode("utf-8")
        headers["X-Iamages-Lock-Nonce"] = b64encode(image.file.nonce).decode("utf-8")
        headers["X-Iamages-Lock-Tag"] = b64encode(image.file.tag).decode("utf-8")

    image_file_name = f"{id}{image.file.type_extension}"
    return FileResponse(
        IMAGES_PATH / image_file_name,
        media_type=image.file.content_type,
        headers=headers,
        filename=image_file_name
    )

@router.api_route(
    "/{id}",
    methods=["GET", "HEAD"],
    response_model=Image,
    response_model_exclude={
        "file": {
            "salt": ...,
            "nonce": ...,
            "tag": ...
        },
        "metadata": ...
    },
    response_model_by_alias=False,
    response_model_exclude_none=True
)
def get_image_information(
    id: PyObjectId,
    user: User | None = Depends(get_optional_user)
):
    return get_image_in_db(id, user)

@router.get(
    "/{id}/metadata",
    response_model=ImageMetadata,
    response_model_exclude_none=True
)
def get_image_metadata(
    id: PyObjectId,
    user: User | None = Depends(get_optional_user)
):
    image = get_image_in_db(id, user)
    if image.lock.is_locked:
        return Response(image.metadata.data, media_type="application/octet-stream", headers={
            "Content-Length": str(len(image.metadata.data)),
            "X-Iamages-Lock-Salt": b64encode(image.metadata.salt).decode("utf-8"),
            "X-iamages-Lock-Nonce": b64encode(image.metadata.nonce).decode("utf-8"),
            "X-Iamages-Lock-Tag": b64encode(image.metadata.tag).decode("utf-8")
        })
    return image.metadata.data

@router.get(
    "/{id}/embed",
    description="Presents the image in a webpage.",
    response_class=HTMLResponse
)
def get_image_embed(
    id: PyObjectId,
    request: Request
):
    image = get_image_in_db(id, None)
    return templates.TemplateResponse("embed-image.html", {
        "request": request,
        "image": jsonable_encoder(
            image,
            by_alias=False,
            exclude_none=True,
            exclude={
                "lock": {
                    "upgradable": ...
                },
                "collections": ...
            }
        ),
        "extension": image.file.type_extension.lstrip(".")
    })

@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def delete_image(
    id: PyObjectId,
    user: User | None = Depends(get_optional_user),
    ownerless_key: UUID | None = Header(None, alias="x-iamages-ownerless-key")
):
    image_dict = db_images.find_one({"_id": id})

    if not image_dict:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    image = ImageInDB.parse_obj(image_dict)

    if not user:
        if not ownerless_key:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="No user token or ownerless key provided.")
        if not image.ownerless_key:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Image belongs to someone else.")
        if not compare_digest(str(image.ownerless_key), str(ownerless_key)):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Ownerless key doesn't match.")
    else:
        if not image.owner:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Image is anonymously uploaded and requires an ownerless key to be deleted.")
        if not compare_digest(image.owner, user.username):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="You don't have permission to delete this image.")

    db_images.find_one_and_delete({"_id": id})

    image_file_name = f"{id}{image.file.type_extension}"
    try:
        (IMAGES_PATH / image_file_name).unlink()
    except FileNotFoundError:
        pass
    try:
        (THUMBNAILS_PATH / image_file_name).unlink()
    except FileNotFoundError:
        pass

@router.patch(
    "/{id}",
    response_model=ImageEditResponse,
    response_model_exclude_none=True
)
def patch_image_information(
    id: PyObjectId,
    change: EditableImageInformation = Body(...),
    to: bool | str = Body(...),
    metadata_lock_key: str | None = Body(None),
    image_lock_key: str | None = Body(None),
    user: User = Depends(get_user)
):
    image_dict = db_images.find_one({"_id": id})
    if not image_dict:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    image = ImageInDB.parse_obj(image_dict)

    if not compare_digest(image.owner, user.username):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="You don't have permission to modify this image's information.")

    match change:
        case EditableImageInformation.is_private:
            if type(to) != bool:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="is_private requires a boolean 'to'.")
            db_images.update_one({"_id": id}, {
                "$set": {
                    "is_private": to
                }
            })
            return ImageEditResponse()
        case EditableImageInformation.description:
            if type(to) != str:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="description requires a string 'to'.")
            if image.lock.is_locked and not metadata_lock_key:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No metadata lock key provided for locked image.")

            image_metadata = image.metadata.data
            if image.lock.is_locked:
                metadata_lock_key_bytes = check_key_len(metadata_lock_key)
                cipher = AES.new(metadata_lock_key_bytes, AES.MODE_GCM, nonce=image.metadata.nonce)
                image_metadata = ImageMetadata.parse_raw(cipher.decrypt_and_verify(image_metadata, image.metadata.tag))
            image_metadata.description = to

            nonce = None
            tag = None

            if image.lock.is_locked:
                image_metadata = orjson.dumps(image_metadata.dict())
                nonce = get_random_bytes(12)
                cipher = AES.new(metadata_lock_key_bytes, AES.MODE_GCM, nonce=nonce)
                image_metadata, tag = cipher.encrypt_and_digest(image_metadata)

            metadata_object = ImageMetadataContainer(
                salt=image.metadata.salt,
                nonce=nonce,
                data=image_metadata,
                tag=tag
            )

            update_dict = {
                "$set": {
                    "metadata": metadata_object.dict(exclude_none=True)
                }
            }
            db_images.update_one({"_id": id}, update_dict)
            return ImageEditResponse()
        case EditableImageInformation.lock:
            if image.lock.is_locked and (not metadata_lock_key or not image_lock_key):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No lock key provided for locked image.")
            # Set a new lock key.
            if type(to) == str:
                # Re-encrypt existing image metadata by decrypting using lock_key
                # and encrypting using to key.
                if image.lock.is_locked:
                    cipher = AES.new(
                        check_key_len(metadata_lock_key),
                        AES.MODE_GCM,
                        nonce=image.metadata.nonce
                    )
                    metadata_data = cipher.decrypt_and_verify(image.metadata.data, image.metadata.tag)
                else:
                    image.metadata.data.real_content_type = image.file.content_type
                    metadata_data = orjson.dumps(image.metadata.data.dict(exclude_none=True))

                metadata_key, metadata_salt = hash_password(to)
                metadata_nonce = get_random_bytes(12)
                cipher = AES.new(metadata_key, AES.MODE_GCM, nonce=metadata_nonce)
                metadata_data, metadata_tag = cipher.encrypt_and_digest(metadata_data)

                # Re-encrypt existing image file by decrypting using lock_key
                # and encrypting using to key.
                file_name = f"{id}{image.file.type_extension}"
                if image.lock.is_locked:
                    cipher = AES.new(
                        check_key_len(image_lock_key),
                        AES.MODE_GCM,
                        nonce=image.file.nonce
                    )
                    with open(IMAGES_PATH / file_name, "rb") as file:
                        file_data = cipher.decrypt_and_verify(file.read(), image.file.tag)
                else:
                    with open(IMAGES_PATH / file_name, "rb") as file:
                        file_data = file.read()

                file_key, file_salt = hash_password(to)
                file_nonce = get_random_bytes(12)
                cipher = AES.new(file_key, AES.MODE_GCM, nonce=file_nonce)
                file_data, file_tag = cipher.encrypt_and_digest(file_data)

                new_file_extension = guess_extension("application/octet-stream")
                if not image.lock.is_locked:
                    (IMAGES_PATH / file_name).unlink()
                with open(IMAGES_PATH / f"{id}{new_file_extension}", "wb") as image_file:
                    image_file.write(file_data)

                db_images.update_one({
                    "_id": id
                }, {
                    "$set": {
                        "lock": {
                            "is_locked": True,
                            "version": LockVersion.aes128gcm_argon2
                        },
                        "file": {
                            "content_type": "application/octet-stream",
                            "type_extension": new_file_extension,
                            "salt": file_salt,
                            "nonce": file_nonce,
                            "tag": file_tag
                        },
                        "metadata": {
                            "salt": metadata_salt,
                            "nonce": metadata_nonce,
                            "data": metadata_data,
                            "tag": metadata_tag
                        }
                    },
                    "$unset": {
                        "thumbnail": None
                    }
                })

                try:
                    (THUMBNAILS_PATH / file_name).unlink()
                except FileNotFoundError:
                    pass
                except Exception as e:
                    raise e

                return ImageEditResponse(
                    lock_version=LockVersion.aes128gcm_argon2,
                    file=File(
                        content_type="application/octet-stream",
                        type_extension=new_file_extension,
                        salt=file_salt
                    ),
                    metadata_salt=metadata_salt
                )
            # Remove a lock
            elif type(to) == bool:
                cipher = AES.new(
                    check_key_len(metadata_lock_key),
                    AES.MODE_GCM,
                    nonce=image.metadata.nonce
                )
                metadata_data = ImageMetadata.parse_raw(cipher.decrypt_and_verify(image.metadata.data, image.metadata.tag))
                content_type = metadata_data.real_content_type
                metadata_data.real_content_type = None

                cipher = AES.new(
                    check_key_len(image_lock_key),
                    AES.MODE_GCM,
                    nonce=image.file.nonce
                )
                file_name = f"{id}{image.file.type_extension}"
                new_file_extension = guess_extension(content_type)
                with (
                    open(IMAGES_PATH / file_name, "rb") as encrypted_file,
                    open(IMAGES_PATH / f"{id}{new_file_extension}", "wb") as decrypted_file
                ):
                    decrypted_file.write(
                        cipher.decrypt_and_verify(encrypted_file.read(), image.file.tag)
                    )

                (IMAGES_PATH / file_name).unlink()

                db_images.update_one({
                    "_id": id
                }, {
                    "$set": {
                        "lock.is_locked": False,
                        "file.content_type": content_type,
                        "file.type_extension": new_file_extension,
                        "metadata.data": metadata_data.dict(exclude_none=True),
                        "thumbnail": Thumbnail().dict()
                    },
                    "$unset": {
                        "lock.version": None,
                        "file.salt": None,
                        "file.nonce": None,
                        "file.tag": None,
                        "metadata.salt": None,
                        "metadata.nonce": None,
                        "metadata.tag": None
                    }
                })

                return ImageEditResponse(
                    file=File(
                        content_type=content_type,
                        type_extension=new_file_extension
                    )
                )
            else:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="to has to be either a string or boolean, depending on what you want to modify.")
