from secrets import compare_digest

from fastapi import APIRouter, Depends, status, HTTPException, Body
from pydantic import conint
from pymongo import DESCENDING

from ..common.db import db_collections, db_images
from ..common.security import get_optional_user, get_user

from ..models.default import PyObjectId
from ..models.collections import Collection, NewCollection, CollectionMetadata, EditableCollectionInformation
from ..models.users import User
from ..models.images import Image
from ..models.pagination import Pagination

def add_images(collection_id: PyObjectId, image_ids: list[PyObjectId], user: User | None):
    for image_id in image_ids:
        image_dict = db_images.find_one({"_id": image_id})
        if not image_dict:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"The image '{image_id}' does not exist.")
        image = Image.parse_obj(image_dict)
        if image.is_private and not compare_digest(image.owner, user.username):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"You don't have permission to access the image '{image_id}'.")
        db_images.update_one({"_id": image_id}, {"$push": {"collections": collection_id}})

router = APIRouter(prefix="/collections")

@router.post(
    "/",
    response_model=Collection,
    response_model_by_alias=False,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED
)
def new_collection(
    new_collection: NewCollection,
    user: User | None = Depends(get_optional_user)
):
    # Create new collection object
    collection = Collection(
        owner=user.username,
        is_private=new_collection.is_private,
        metadata=CollectionMetadata(
            description=new_collection.description
        )
    )
    db_collections.insert_one(collection.dict(by_alias=True, exclude={"created_on"}))
    # Validate images list.
    add_images(collection.id, new_collection.image_ids, user)
    return collection

@router.get(
    "/{id}",
    response_model=Collection,
    response_model_by_alias=False,
    response_model_exclude_none=True
)
def get_collection(
    id: PyObjectId,
    user: User | None = Depends(get_optional_user)
):
    collection_dict = db_collections.find_one({"_id": id})
    if not collection_dict:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    collection = Collection.parse_obj(collection_dict)
    if collection.is_private and compare_digest(user.username, collection.owner):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    return collection

@router.patch(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def edit_collection(
    id: PyObjectId,
    change: EditableCollectionInformation = Body(...),
    to: bool | str | list[PyObjectId] = Body(...),
    user: User = Depends(get_user)
):
    collection_dict = db_collections.find_one({"_id": id})
    if not collection_dict:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    collection = Collection.parse_obj(collection_dict)
    if not compare_digest(collection.owner, user.username):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    match change:
        case EditableCollectionInformation.description:
            if type(to) != str:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="description requires a string 'to'.")
            db_collections.update_one({"_id": id}, {
                "$set": {
                    "description": to
                }
            })
        case EditableCollectionInformation.is_private:
            if type(to) != bool:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="is_private requires a boolean 'to'.")
            db_collections.update_one({"_id": id}, {
                "$set": {
                    "is_private": to
                }
            })
        case EditableCollectionInformation.add_images:
            if type(to) != list:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="add_images requires a list of ids 'to'.")
            add_images(id, to, user)
        case EditableCollectionInformation.remove_images:
            if type(to) != list:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="remove_images requires a list of ids 'to'.")
            for image_id in to:
                db_images.update_one({"_id": image_id}, {"$pull": {"collection": id}})

@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def delete_collection(
    id: PyObjectId,
    user: User = Depends(get_user)
):
    collection_dict = db_collections.find_one({"_id": id})
    if not collection_dict:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    collection = Collection.parse_obj(collection_dict)
    if not compare_digest(collection.owner, user.username):
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    db_collections.delete_one({"_id": id})
    db_images.update_many(
        {"collection": id},
        {"$pull": {"collection": id}}
    )

@router.post(
    "/{id}/images",
    response_model=list[Image],
    response_model_by_alias=False,
    response_model_exclude_none=True
)
def get_collection_images(
    id: PyObjectId,
    pagination: Pagination,
    user: User | None = Depends(get_optional_user)
):
    filters = {"collections": id}
    if not user:
        filters["is_private"] = False
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
    image_dicts = list(db_images.find(filters).sort("_id", DESCENDING).limit(pagination.limit))
    if user:
        for i, image in enumerate(map(lambda image_dict: Image.parse_obj(image_dict), image_dicts)):
            if image.is_private and user and not compare_digest(image.owner, user.username):
                del image_dicts[i]
    return image_dicts

@router.post(
    "/{id}/images/suggestions",
    response_model=list[str]
)
def get_collection_images_query_suggestions(
    id: PyObjectId,
    query: str = Body(...),
    user: User | None = Depends(get_optional_user)
):
    filters = {
        "collection": id,
        "lock.is_locked": False,
        "metadata.data.description": {
            "$regex": query,
            "$options": "i"
        }
    }
    if not user:
        filters["is_private"] = False
    image_dicts = list(db_images.find(filters).sort("_id", DESCENDING).limit(6))
    if user:
        for i, image in enumerate(map(lambda image_dict: Image.parse_obj(image_dict), image_dicts)):
            if image.is_private and user and not compare_digest(image.owner, user.username):
                del image_dicts[i]
    return list(
        map(
            lambda i: i["metadata"]["data"]["description"],
            image_dicts
        )
    )