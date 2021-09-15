from datetime import datetime
from enum import Enum
from typing import Optional, Union

from fastapi import (APIRouter, Body, Depends, HTTPException, Query, Request,
                     status)
from fastapi.responses import HTMLResponse

from ..common.auth import (auth_optional_dependency, auth_required_dependency,
                           compare_owner)
from ..common.db import get_conn, r
from ..common.paths import FILES_PATH, THUMBS_PATH
from ..common.utils import handle_str2bool
from ..modals.collection import CollectionBase, CollectionInDB
from ..modals.file import FileBase, FileInDB
from ..modals.user import UserBase

router = APIRouter(
    prefix="/collection",
    tags=["collection"]
)

@router.get(
    "/{id}/info",
    response_model=CollectionBase,
    description="Gets information about a collection."
)
def info(
    id: str,
    user: Optional[UserBase] = Depends(auth_optional_dependency)
):
    with get_conn() as conn:
        collection_information = r.table("collections").get(str(id)).run(conn)
    if not collection_information:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    
    collection_information_parsed = CollectionInDB.parse_obj(collection_information)
    if not collection_information_parsed.private:
        return collection_information

    if not compare_owner(collection_information_parsed, user):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)

    return collection_information

@router.post(
    "/{id}/files",
    response_model=list[FileBase],
    description="Gets the files in a collection."
)
def files(
    id: str,
    limit: Optional[int] = Body(None, description="Limit search results."),
    start_date: Optional[datetime] = Body(None, description="Date to start searching from."),
    user: Optional[UserBase] = Depends(auth_optional_dependency),
):
    with get_conn() as conn:
        collection_information = r.table("collections").get(id).run(conn)
        if not collection_information:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        
        collection_information_parsed = CollectionInDB.parse_obj(collection_information)
        if not collection_information_parsed.private or compare_owner(collection_information_parsed, user):
            filters = (r.row["collection"] == id)

            if start_date:
                filters = filters & (r.row["created"] < start_date)

            query = r.table("files").filter(filters).order_by(r.desc("created"))
            if limit:
                query.limit(limit)
            
            files = query.run(conn)

            approved_files = []
            for file in files:
                file_information_parsed = FileInDB.parse_obj(file)
                if not file_information_parsed.private or compare_owner(file_information_parsed, user):
                    approved_files.append(file)

            return approved_files
        else:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED)


class CollectionModifiableFields(str, Enum):
    description = "description"
    private = "private"
    hidden = "hidden"
    add_file = "add_file"
    remove_file = "remove_file"

@router.patch(
    "/{id}/modify",
    status_code=status.HTTP_204_NO_CONTENT,
    description="Modifies an existing collection."
)
def modify(
    id: str,
    field: CollectionModifiableFields = Body(..., description="Data field to modify for the collection."),
    data: Union[bool, str] = Body(..., description="Data given to the `field`."),
    user: UserBase = Depends(auth_required_dependency)
):
    with get_conn() as conn:
        query = r.table("collections").get(id)

        collection_information = query.run(conn)
        if not collection_information:
            raise HTTPException(status.HTTP_404_NOT_FOUND)

        collection_information_parsed = CollectionInDB.parse_obj(collection_information)
        if not compare_owner(collection_information_parsed, user):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED)

        if field == CollectionModifiableFields.description:
            query.update({
                "description": str(data)
            }).run(conn)
        elif field == CollectionModifiableFields.private:
            query.update({
                "private": handle_str2bool(data)
            }).run(conn)
        elif field == CollectionModifiableFields.hidden:
            query.update({
                "hidden": handle_str2bool(data)
            }).run(conn)
        elif field == CollectionModifiableFields.add_file:
            if not r.table("files").get_all(str(data)).count().eq(1).run(conn):
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"File ID not found: {data}")
            r.table("files").get(str(data)).update({
                "collection": id
            }).run(conn)
        elif field == CollectionModifiableFields.remove_file:
            if r.table("files").get_all(str(data)).count().eq(1).run(conn):
                r.table("files").get(str(data)).update({
                    "collection": r.literal()
                }).run(conn)

@router.delete(
    "/{id}/delete",
    status_code=status.HTTP_204_NO_CONTENT,
    description="Deletes a collection. (and optionally, its files)"
)
def delete(
    id: str,
    delete_files: bool = Query(False, description="Delete files in the collection too."),
    user: UserBase = Depends(auth_required_dependency)
):
    pass

@router.get(
    "/{id}/embed",
    response_class=HTMLResponse,
    name="embed",
    description="Gets embed for a collection."
)
def embed(
    request: Request,
    id: str
):
    pass
