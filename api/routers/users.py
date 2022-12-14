from datetime import datetime, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestFormStrict
from jose import jwt
from passlib.context import CryptContext

from ..common.db import db_users
from ..common.security import (ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM,
                               get_user)
from ..common.settings import api_settings
from ..models.tokens import JWTModal, Token
from ..models.users import User, UserInDB

crypt_context = CryptContext(schemes=["argon2"], deprecated=["auto"])
router = APIRouter(prefix="/users")

@router.post(
    "/",
    response_model=User,
    response_model_by_alias=False
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

@router.get(
    "/",
    response_model=User,
    response_model_by_alias=False
)
def get_user_information(
    user: User = Depends(get_user)
):
    return user
