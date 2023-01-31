from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from ..models.users import User
from .db import db_users
from .settings import api_settings

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/user/token")
oauth2_optional_scheme = OAuth2PasswordBearer(tokenUrl="/user/token", auto_error=False)

def common_get_user(token: str) -> User:
    try:
        payload = jwt.decode(token, api_settings.jwt_secret, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    if not username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    user_dict = db_users.find_one({
        "_id": username
    })
    if not user_dict:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    user = User.parse_obj(user_dict)
    return user

def get_user(token: str = Depends(oauth2_scheme)) -> User:
    return common_get_user(token)

def get_optional_user(token: str | None = Depends(oauth2_optional_scheme)) -> User | None:
    if not token:
        return None
    return common_get_user(token)
