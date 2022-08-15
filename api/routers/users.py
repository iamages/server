from datetime import datetime, timedelta

from anyio.to_thread import run_sync
from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestFormStrict
from jose import jwt

from ..common.db import db
from ..common.security import (ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM,
                               crypt_context)
from ..common.settings import api_settings
from ..models.tokens import JWTModal, Token
from ..models.users import UserInDB, User

collection = db.users
router = APIRouter(prefix="/users")

@router.post(
    "/",
    response_model=User,
    response_model_by_alias=False
)
async def new_user(
    username: str = Body(),
    password: str = Body()
):
    if await collection.count_documents({
        "_id": username
    }, limit=1) != 0:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This username is already taken.")

    user = UserInDB(
        username=username,
        password=await run_sync(lambda: crypt_context.hash(password))
    )

    user_dict = user.dict(by_alias=True)
    
    await collection.insert_one(user_dict)

    return user_dict

@router.post(
    "/token",
    response_model=Token
)
async def get_user_token(
    form: OAuth2PasswordRequestFormStrict = Depends()
):
    user_dict = await collection.find_one({
        "_id": form.username
    })

    if not user_dict:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="User not found. Try signing up first.")

    user = UserInDB.parse_obj(user_dict)

    password_check_results = await run_sync(lambda: crypt_context.verify_and_update(form.password, user.password))

    if not password_check_results[0]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Password is incorrect.")

    if password_check_results[1]:
        await collection.update_one({
            "_id": user.username
        }, {
            "$set": {
                "password": password_check_results[1]
            }
        })

    jwt_dict = JWTModal(sub=user.username, exp=datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).dict()

    return Token(access_token=jwt.encode(jwt_dict, api_settings.jwt_secret, algorithm=JWT_ALGORITHM))
