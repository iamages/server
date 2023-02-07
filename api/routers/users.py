from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from secrets import compare_digest
from smtplib import SMTP

from fastapi import (APIRouter, BackgroundTasks, Body, Depends, HTTPException,
                     Request, Response, status)
from fastapi.security import OAuth2PasswordRequestFormStrict
from jose import jwt
from passlib.context import CryptContext
from pydantic import EmailStr
from pydantic.errors import EmailError
from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError

from ..common.db import db, db_collections, db_images, db_users
from ..common.paths import IMAGES_PATH, THUMBNAILS_PATH
from ..common.security import (ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM,
                               get_user)
from ..common.settings import api_settings
from ..common.templates import templates
from ..models.collections import Collection
from ..models.images import Image
from ..models.pagination import Pagination
from ..models.tokens import JWTModal, Token
from ..models.users import (EditableUserInformation, PasswordReset, User,
                            UserInDB)

db_password_resets = db.password_resets

def perform_user_delete(username: str):
    db_users.delete_one({"_id": username})
    image_ids = db_images.find({"owner": username}, {"_id": 1, "file.type_extension": 1})
    for image_dict in image_ids:
        id = image_dict["_id"]
        db_images.delete_one({"_id": id})
        filename = f"{id}{image_dict['file']['type_extension']}"
        (IMAGES_PATH / filename).unlink(True)
        (THUMBNAILS_PATH / filename).unlink(True)
    db_collections.delete_many({"owner": username})

crypt_context = CryptContext(schemes=["argon2"], deprecated=["auto"])
router = APIRouter(prefix="/users")

@router.post(
    "/",
    response_model=User,
    response_model_by_alias=False,
    status_code=status.HTTP_201_CREATED
)
def new_user(
    username: str = Body(min_length=3),
    password: str = Body(min_length=6),
    email: EmailStr | None = Body(None)
):
    if db_users.count_documents({
        "_id": username
    }, limit=1) != 0:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This username is already taken.")

    user = UserInDB(
        username=username,
        password=crypt_context.hash(password),
        email=email
    )

    user_dict = user.dict(by_alias=True, exclude_none=True)
    
    db_users.insert_one(user_dict)

    return user_dict

@router.get(
    "/",
    response_model=User,
    response_model_by_alias=False
)
def get_user_information(
    user: User = Depends(get_user)
):
    return user

@router.patch(
    "/",
    status_code=status.HTTP_204_NO_CONTENT
)
def patch_user_information(
    change: EditableUserInformation = Body(...),
    to: str | None = Body(None),
    user: User = Depends(get_user)
):
    match change:
        case EditableUserInformation.email:
            # to is None, remove user's email.
            if not to:
                db_users.update_one({"_id": user.username}, {
                    "$unset": {"email": 0}
                })
                return
            # Validate to is email and set new email.
            try:
                email = EmailStr(to)
            except EmailError:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Not a valid email.")
            db_users.update_one({"_id": user.username}, {
                "$set": {
                    "email": email
                }
            })
        case EditableUserInformation.password:
            if not to:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Password not provided.")
            db_users.update_one({"_id": user.username}, {
                "$set": {
                    "password": crypt_context.hash(to)
                }
            })

@router.delete(
    "/",
    status_code=status.HTTP_202_ACCEPTED
)
def delete_user(
    background_tasks: BackgroundTasks,
    user: User = Depends(get_user)
):
    background_tasks.add_task(perform_user_delete, username=user.username)

@router.post(
    "/token",
    response_model=Token
)
def get_user_token(
    form: OAuth2PasswordRequestFormStrict = Depends()
):
    user_dict = db_users.find_one({
        "_id": form.username
    })

    if not user_dict:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="User not found. Try signing up first.")

    user = UserInDB.parse_obj(user_dict)

    password_check_results = crypt_context.verify_and_update(form.password, user.password)

    if not password_check_results[0]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Password is incorrect. Check your password.")

    if password_check_results[1]:
        db_users.update_one({
            "_id": user.username
        }, {
            "$set": {
                "password": password_check_results[1]
            }
        })

    jwt_dict = JWTModal(sub=user.username, exp=datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).dict()

    return Token(access_token=jwt.encode(jwt_dict, api_settings.jwt_secret, algorithm=JWT_ALGORITHM))

@router.post(
    "/password/code",
    status_code=status.HTTP_201_CREATED
)
def get_password_reset_code(
    request: Request,
    email: EmailStr = Body(...)
):
    user_dict = db_users.find_one({"email": email})
    if not user_dict:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    
    password_reset = PasswordReset(email=email)
    
    try:
        db_password_resets.insert_one(password_reset.dict(by_alias=True))
    except DuplicateKeyError:
        return Response(status.HTTP_200_OK)
    except Exception as e:
        print(str(e))

    message = MIMEMultipart('alternative')
    message["Subject"] = "Reset Iamages account password"
    message["From"] = formataddr(("Iamages", api_settings.smtp_from)) 
    message["To"] = email
    message.attach(
        MIMEText(
            templates.get_template("forgot-password.txt").render({
                "request": request,
                "code": password_reset.code
            }),
            "plain"
        )
    )
    message.attach(
        MIMEText(
            templates.get_template("forgot-password.html").render({
                "request": request,
                "code": password_reset.code
            }),
            "html"
        )
    )
    with SMTP(api_settings.smtp_host, api_settings.smtp_port) as smtp:
        if api_settings.smtp_starttls:
            smtp.starttls()
        if api_settings.smtp_username and api_settings.smtp_password:
            smtp.login(api_settings.smtp_username, api_settings.smtp_password)
        smtp.send_message(message)

@router.post(
    "/password/reset"
)
def reset_password(
    email: EmailStr = Body(...),
    code: str = Body(...),
    new_password: str = Body(...)
):
    user_dict = db_users.find_one({"email": email})
    if not user_dict:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    password_reset_dict = db_password_resets.find_one({"_id": email})
    if not password_reset_dict:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    password_reset = PasswordReset.parse_obj(password_reset_dict)
    if (datetime.now(timezone.utc) - password_reset.created_on).total_seconds() > 900:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="The code has expired.")
    if not compare_digest(code, password_reset.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="The password reset code is incorrect.")
    db_users.update_one({"_id": user_dict["_id"]}, {
        "$set": {
            "password": crypt_context.hash(new_password)
        }
    })
    db_password_resets.delete_one({"_id": email})

@router.post(
    "/images",
    response_model=list[Image],
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
def get_user_images(
    pagination: Pagination,
    user: User = Depends(get_user)
):
    filters = {
        "owner": user.username
    }
    if pagination.query:
        filters["lock.is_locked"] = False
        filters["metadata.data.description"] = {
            "$regex": pagination.query,
            "$options": "i"
        }
    if pagination.last_id:
        filters["_id"] = {
            "$lt": pagination.last_id
        }
    return list(db_images.find(filters).sort("_id", DESCENDING).limit(pagination.limit))

@router.post(
    "/images/suggestions",
    response_model=list[str]
)
def get_images_query_suggestions(
    query: str = Body(...),
    user: User = Depends(get_user)
):
    return list(
        map(
            lambda i: i["metadata"]["data"]["description"],
            db_images.find({
                "owner": user.username,
                "lock.is_locked": False,
                "metadata.data.description": {
                    "$regex": query,
                    "$options": "i"
                }
            })
            .sort("_id", DESCENDING)
            .limit(6)
        )
    )

@router.post(
    "/collections",
    response_model=list[Collection],
    response_model_by_alias=False
)
def get_user_collections(
    pagination: Pagination,
    user: User = Depends(get_user)
):
    filters = {
        "owner": user.username
    }
    if pagination.query:
        filters["description"] = pagination.query
    if pagination.last_id:
        filters["_id"] = {
            "$lt": pagination.last_id
        }
    return list(db_collections.find(filters).sort("_id", DESCENDING).limit(pagination.limit))

@router.post(
    "/collections/suggestions",
    response_model=list[str],
    response_model_by_alias=False
)
def get_collections_query_suggestions(
    query: str = Body(...),
    user: User = Depends(get_user)
):
    return list(
        map(
            lambda i: i["metadata"]["data"]["description"],
            db_collections.find({
                "owner": user.username,
                "metadata.data.description": {
                    "$regex": query,
                    "$options": "i"
                }
            })
            .sort("_id", DESCENDING)
            .limit(6)
        )
    )
