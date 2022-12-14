from base64 import b64decode, b64encode
from io import BytesIO
from mimetypes import guess_extension
from typing import BinaryIO
from uuid import UUID, uuid4
from secrets import compare_digest

import magic
import orjson
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from fastapi import (APIRouter, Depends, Form, Header, HTTPException, Query,
                     UploadFile, status, Body)
from fastapi.responses import Response, StreamingResponse
from gridfs.errors import NoFile as GridFSNoFile
from passlib.hash import argon2
from PIL import Image as PillowImage
from pydantic import Json

from ..common.db import db_images, fs_images, fs_thumbnails, yield_grid_file
from ..common.security import get_optional_user, get_user
from ..common.settings import api_settings
from ..models.default import PyObjectId
from ..models.images import (Image, ImageInDB, ImageInformationType,
                             ImageMetadata, ImageUpload, Lock, LockVersion,
                             Metadata, Thumbnail, EditableImageInformation, ImageEditResponse)
from ..models.users import User

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

router = APIRouter(prefix="/images")

@router.post(
    "/",
    response_model=Image,
    response_model_by_alias=False,
    response_model_exclude_unset=True
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

    with PillowImage.open(file.file) as original_file:
        width, height = original_file.size

        image_metadata = ImageMetadata(
            description=information.description,
            width=width,
            height=height,
            real_content_type=mime if information.is_locked else None
        )

        image_metadata_bytes = orjson.dumps(image_metadata.dict())
        nonce = None
        tag = None

        key = None
        salt = None

        if information.is_locked:
            key, salt = hash_password(information.lock_key)

            nonce = get_random_bytes(12)

            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)

            image_metadata_bytes, tag = cipher.encrypt_and_digest(image_metadata_bytes)

        image = ImageInDB(
            is_private=information.is_private,
            content_type="application/octet-stream" if information.is_locked else mime,
            lock=Lock(
                is_locked=information.is_locked,
                version=LockVersion.aes128gcm_argon2 if information.is_locked else None
            ),
            thumbnail=Thumbnail(),
            metadata=Metadata(
                salt=salt,
                nonce=nonce,
                data=image_metadata_bytes,
                tag=tag,
            )
        )

        if user:
            image.owner = user.username

        insert_result = db_images.insert_one(image.dict(by_alias=True, exclude_none=True, exclude={"created_on"}))

        with (
            PillowImage.new(original_file.mode, (width, height)) as new_file,
            BytesIO() as temporary
        ):
            new_file.putdata(original_file.getdata())

            if mime == "image/gif":
                new_file.save(temporary, format=original_file.format, save_all=True)
            else:
                new_file.save(temporary, format=original_file.format)

            gridfs_source = temporary.getvalue()

            image_file_metadata = {
                "content_type": "application/octet-stream" if information.is_locked else mime,
            }

            if information.is_locked:
                key, salt = hash_password(information.lock_key)
                image_file_metadata["salt"] = salt

                nonce = get_random_bytes(12)
                image_file_metadata["nonce"] = nonce

                cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)

                gridfs_source, tag = cipher.encrypt_and_digest(gridfs_source)
                gridfs_source = BytesIO(gridfs_source)

                image_file_metadata["tag"] = tag

            fs_images.upload_from_stream_with_id(
                insert_result.inserted_id,
                f"{insert_result.inserted_id}{'' if information.is_locked else guess_extension(mime)}",
                gridfs_source,
                metadata=image_file_metadata
            )

    if not user:
        ownerless_key = uuid4()

        db_images.update_one({
            "_id": insert_result.inserted_id
        }, {
            "$set": {
                "ownerless_key": ownerless_key
            }
        })

        response.headers["X-Iamages-Ownerless-Key"] = str(ownerless_key)

    return Image(**image.dict())

@router.get(
    "/{id}/download",
    response_class=StreamingResponse
)
def get_image_file(
    id: PyObjectId,
    user: User | None = Depends(get_optional_user)
):
    image_dict = db_images.find_one({
        "_id": id
    })

    if not image_dict:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    image = ImageInDB.parse_obj(image_dict)

    if image.is_private and (not user or image.owner != user.username):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="You don't have permission to view this image.")

    image_grid_out = fs_images.open_download_stream(image.id)

    headers = {
        "Content-Length": str(image_grid_out.length)
    }

    if image.lock.is_locked:
        headers["X-Iamages-Lock-Salt"] = b64encode(image_grid_out.metadata["salt"]).decode("utf-8")
        headers["X-Iamages-Lock-Nonce"] = b64encode(image_grid_out.metadata["nonce"]).decode("utf-8")
        headers["X-Iamages-Lock-Tag"] = b64encode(image_grid_out.metadata["tag"]).decode("utf-8")

    return StreamingResponse(
        yield_grid_file(image_grid_out),
        media_type=image_grid_out.metadata["content_type"],
        headers=headers
    )

@router.api_route(
    "/{id}",
    methods=["GET", "HEAD"],
    response_model=Image,
    response_model_by_alias=False
)
def get_image_information(
    id: PyObjectId,
    information_type: ImageInformationType = Query(ImageInformationType.public, alias="type"),
    user: User | None = Depends(get_optional_user)
):
    image_dict = db_images.find_one({
        "_id": id
    })

    if not image_dict:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    image = ImageInDB.parse_obj(image_dict)

    if image.is_private and (not user or image.owner != user.username):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="You don't have permission to view this image.")

    match information_type:
        case ImageInformationType.public:
            return image
        case ImageInformationType.private:
            headers = {
                "Content-Length": str(len(image.metadata.data))
            }
            if image.lock.is_locked:
                headers["X-Iamages-Lock-Salt"] = b64encode(image.metadata.salt).decode("utf-8")
                headers["X-Iamages-Lock-Nonce"] = b64encode(image.metadata.nonce).decode("utf-8")
                headers["X-Iamages-Lock-Tag"] = b64encode(image.metadata.tag).decode("utf-8")
            return Response(image.metadata.data, media_type="application/octet-stream", headers=headers)

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
        if not compare_digest(image.ownerless_key, ownerless_key):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Ownerless key doesn't match.")
    else:
        if not image.owner:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Image is anonymously uploaded and requires an ownerless key to be deleted.")
        if not compare_digest(image.owner, user.username):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="You don't have permission to delete this image.")

    db_images.find_one_and_delete({"_id": id})
    try:
        fs_images.delete(id)
        fs_thumbnails.delete(id)
    except GridFSNoFile:
        pass
    except Exception as e:
        print(str(e))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Couldn't delete image/thumbnail file.")

@router.patch(
    "/{id}",
    response_model=ImageEditResponse
)
def patch_image_information(
    id: PyObjectId,
    change: EditableImageInformation = Body(...),
    to: bool | str = Body(...),
    lock_key: str | None = Body(None),
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
            if image.lock.is_locked and not lock_key:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No lock key provided for locked image.")

            image_metadata_bytes = image.metadata.data
            if image.lock.is_locked:
                cipher = AES.new(hash_password(lock_key, image.metadata.salt)[0], AES.MODE_GCM, nonce=image.metadata.nonce)
                image_metadata_bytes = cipher.decrypt_and_verify(image_metadata_bytes, image.metadata.tag)

            image_metadata = ImageMetadata.parse_raw(image_metadata_bytes)
            image_metadata.description = to
            image_metadata_bytes = orjson.dumps(image_metadata.dict())

            salt = None
            nonce = None
            tag = None
            
            if image.lock.is_locked:
                key, salt = hash_password(lock_key)
                nonce = get_random_bytes(12)
                cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                image_metadata_bytes, tag = cipher.encrypt_and_digest(image_metadata_bytes)

            metadata_object = Metadata(
                salt=salt,
                nonce=nonce,
                data=image_metadata_bytes,
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
            if image.lock.is_locked and not lock_key:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No lock key provided for locked image.")
            # Set a new lock key.
            if type(to) == str:
                image_grid_out = fs_images.open_download_stream(id)

                if image.lock.is_locked:
                    # Re-encrypt existing image metadata by decrypting using lock_key
                    # and encrypting using to key.
                    cipher = AES.new(
                        hash_password(lock_key, image.metadata.salt)[0],
                        AES.MODE_GCM,
                        nonce=image.metadata.nonce
                    )
                    decrypted_image_metadata = cipher.decrypt_and_verify(image.metadata.data, image.metadata.tag)

                    key, salt = hash_password(to)
                    nonce = get_random_bytes(12)
                    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                    encrypted_image_metadata, tag = cipher.encrypt_and_digest(decrypted_image_metadata)

                    db_images.update_one({
                        "_id": id
                    }, {
                        "$set": {
                            "metadata": {
                                "salt": salt,
                                "nonce": nonce,
                                "data": encrypted_image_metadata,
                                "tag": tag
                            }
                        }
                    })

                    # Re-encrypt existing image file by decrypting using lock_key
                    # and encrypting using to key.
                    cipher = AES.new(
                        hash_password(lock_key, image_grid_out.metadata["salt"])[0],
                        AES.MODE_GCM,
                        nonce=image_grid_out.metadata["nonce"]
                    )
                    decrypted_image_bytes = cipher.decrypt_and_verify(image_grid_out.read(), image_grid_out.metadata["tag"])

                    key, salt = hash_password(to)
                    nonce = get_random_bytes(12)
                    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                    encrypted_image_bytes, tag = cipher.encrypt_and_digest(decrypted_image_bytes)

                    fs_images.delete(id)
                    fs_images.upload_from_stream_with_id(
                        id,
                        f"{id}.bin",
                        encrypted_image_bytes,
                        metadata={
                            "content_type": "application/octet-stream",
                            "salt": salt,
                            "nonce": nonce,
                            "tag": tag
                        })
                else:
                    # Encrypt image metadata
                    key, salt = hash_password(to)
                    nonce = get_random_bytes(12)
                    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)

                    encrypted_image_metadata, tag = cipher.encrypt_and_digest(image.metadata.data)

                    db_images.update_one({
                        "_id", id
                    }, {
                        "$set": {
                            "metadata": {
                                "salt": salt,
                                "nonce": nonce,
                                "data": encrypted_image_metadata,
                                "tag": tag
                            },
                            "lock": {
                                "is_locked": True,
                                "version": LockVersion.aes128gcm_argon2
                            }
                        },
                        "$unset": "thumbnail"
                    })

                    # Encrypt image file
                    key, salt = hash_password(to)
                    nonce = get_random_bytes(12)
                    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)

                    image_grid_out = fs_images.open_download_stream(id)

                    encrypted_image_bytes, tag = cipher.encrypt_and_digest(image_grid_out.read())

                    fs_images.delete(id)
                    fs_images.upload_from_stream_with_id(
                        id,
                        image_grid_out.filename,
                        encrypted_image_bytes,
                        metadata={
                            "content_type": "application/octet-stream",
                            "salt": salt,
                            "nonce": nonce,
                            "tag": tag
                        }
                    )
                    fs_thumbnails.delete(id)
                return ImageEditResponse(lock_version=LockVersion.aes128gcm_argon2)
            # Remove a lock
            elif type(to) == bool and not to:
                cipher = AES.new(hash_password(lock_key, image.metadata.salt)[0], AES.MODE_GCM, nonce=image.metadata.nonce)
                db_images.update_one({
                    "_id": id
                }, {
                    "$set": {
                        "lock.is_locked": False,
                        "metadata.data": cipher.decrypt_and_verify(image.metadata.data, image.metadata.tag)
                    },
                    "$unset": {
                        "lock.version": None,
                        "metadata.salt": None,
                        "metadata.nonce": None,
                        "metadata.tag": None
                    }
                })
                image_grid_out = fs_images.open_download_stream(id)
                cipher = AES.new(hash_password(lock_key, image_grid_out.metadata["salt"])[0], AES.MODE_GCM, nonce=image_grid_out.metadata["nonce"])
                decrypted_image_bytes = cipher.decrypt_and_verify(image_grid_out.read(), image_grid_out.metadata["tag"])
                fs_images.delete(id)
                fs_images.upload_from_stream_with_id(
                    id, image_grid_out.filename, decrypted_image_bytes,
                    metadata={
                        "content_type": image_grid_out.metadata["content_type"],
                    }
                )
            else:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="to has to be either a string or boolean, depending on what you want to modify.")
            

            
            
