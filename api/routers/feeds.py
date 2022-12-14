from fastapi import APIRouter, Depends
from pydantic import conint
from pymongo import DESCENDING

from ..common.db import db_collections, db_images
from ..common.security import get_user
from ..models.collections import Collection
from ..models.default import PyObjectId
from ..models.images import Image
from ..models.users import User

router = APIRouter(prefix="/feeds")

@router.get(
    "/images",
    response_model=list[Image],
    response_model_by_alias=False
)
def get_user_images(
    previous_id: PyObjectId | None = None,
    limit: conint(gt=1, lt=15) = 3,
    user: User = Depends(get_user)
):
    filters = {
        "owner": user.username
    }
    if previous_id:
        filters["$lt"] = {
            "_id": previous_id
        }
    images_dict = db_images.find(filters).sort("_id", DESCENDING).limit(limit)

    return list(images_dict)

@router.get(
    "/collections",
    response_model=list[Collection],
    response_model_by_alias=False
)
def get_user_collections(
    previous_id: PyObjectId | None = None,
    limit: conint(gt=1, lt=15) = 3,
    user: User = Depends(get_user)
):
    filters = {
        "owner": user.username
    }
    if previous_id:
        filters["$lt"] = {
            "_id": previous_id
        }
    images_dict = db_collections.find(filters).sort("_id", DESCENDING).limit(limit)

    return list(images_dict)