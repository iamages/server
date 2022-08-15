from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from ..models.users import User
from .db import db
from .settings import api_settings

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/user/token")
oauth2_optional_scheme = OAuth2PasswordBearer(tokenUrl="/user/token", auto_error=False)
collection = db.users

crypt_context = CryptContext(schemes=["argon2"], deprecated=["auto"])

async def common_get_user(token: str) -> User:
    try:
        payload = jwt.decode(token, api_settings.jwt_secret, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    if not username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    user_dict = await collection.find_one({
        "_id": username
    })
    if not user_dict:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    user = User.parse_obj(user_dict)
    return user

async def get_user(token: str = Depends(oauth2_scheme)) -> User:
    return await common_get_user(token)

async def get_optional_user(token: str | None = Depends(oauth2_optional_scheme)) -> User | None:
    if not token:
        return None
    return await common_get_user(token)
