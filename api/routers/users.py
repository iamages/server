from datetime import datetime, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestFormStrict
from jose import jwt
from passlib.context import CryptContext
from pydantic import conint
from pymongo import DESCENDING

from ..common.db import db_collections, db_images, db_users
from ..common.security import (ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM,
                               get_user)
from ..common.settings import api_settings
from ..models.collections import Collection
from ..models.default import PyObjectId
from ..models.images import Image
from ..models.tokens import JWTModal, Token
from ..models.users import User, UserInDB
from ..models.pagination import Pagination

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
    password: str = Body(min_length=6)
):
    if db_users.count_documents({
        "_id": username
    }, limit=1) != 0:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This username is already taken.")

    user = UserInDB(
        username=username,
        password=crypt_context.hash(password)
    )

    user_dict = user.dict(by_alias=True)
    
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
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Password is incorrect.")

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
    "/images",
    response_model=list[Image],
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
        filters["$lt"] = {
            "_id": pagination.last_id
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
        filters["metadata.description"] = pagination.query
    if pagination.last_id:
        filters["$lt"] = {
            "_id": pagination.last_id
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
