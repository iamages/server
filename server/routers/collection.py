from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Union

import shortuuid
from fastapi import (APIRouter, Body, Depends, HTTPException, Query, Request,
                     status)
from fastapi.responses import HTMLResponse

from ..common.auth import (auth_optional_dependency, auth_required_dependency,
                           compare_owner)
from ..common.db import get_conn, r
from ..common.paths import FILES_PATH, THUMBS_PATH
from ..common.templates import templates
from ..common.utils import handle_str2bool
from ..modals.collection import Collection
from ..modals.file import FileBase, FileInDB, FilesInDB
from ..modals.user import UserBase

router = APIRouter(
    prefix="/collection",
    tags=["collection"]
)

@router.post(
    "/new",
    response_model=Collection,
    status_code=status.HTTP_201_CREATED,
    description="Creates a new collection."
)
def new(
    description: str = Body(...),
    private: bool = Body(False, description="File privacy status. (only visible to user, requires `authorization`)"),
    hidden: bool = Body(False, description="File hiding status. (visible to anyone with `id`, through links, does not show up in public lists)"),
    file_ids: set[str] = Body(..., description="File IDs to add to collection."),
    user: Optional[UserBase] = Depends(auth_optional_dependency)
):
    if not user and private:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    with get_conn() as conn:
        for file_id in file_ids:
            file_information = r.table("files").get(file_id).run(conn)
            if not file_information:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"File ID not found: {file_id}")
            file_information_parsed = FileInDB.parse_obj(file_information)
            if file_information_parsed.private and not compare_owner(file_information_parsed, user):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=f"You don't have permission for File ID: {file_id}")
    
        collection_information_parsed = Collection(
            id=shortuuid.uuid(),
            description=description,
            private=False,
            hidden=hidden,
            created=datetime.now(timezone.utc)
        )

        if user:
            collection_information_parsed.owner = user.username
            if private:
                collection_information_parsed.private = private

        collection_information = collection_information_parsed.dict(exclude_unset=True)

        r.table("collections").insert(collection_information).run(conn)

        for file_id in file_ids:
            r.table("files").get(file_id).update({
                "collection": collection_information_parsed.id
            }).run(conn)

        return collection_information

@router.get(
    "/{id}/info",
    response_model=Collection,
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
    
    collection_information_parsed = Collection.parse_obj(collection_information)
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
        
        collection_information_parsed = Collection.parse_obj(collection_information)
        if not collection_information_parsed.private or compare_owner(collection_information_parsed, user):
            filters = (r.row["collection"] == id)

            if start_date:
                filters = filters & (r.row["created"] < start_date)

            query = r.table("files").filter(filters).order_by(r.desc("created"))
            if limit:
                query = query.limit(limit)

            return [file for file in FilesInDB.parse_obj(query.run(conn)).__root__ if not file.private or compare_owner(file, user)]
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

        collection_information_parsed = Collection.parse_obj(collection_information)
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
    with get_conn() as conn:
        query = r.table("collections").get(id)

        collection_information = query.run(conn)
        if not collection_information:
            raise HTTPException(status.HTTP_404_NOT_FOUND)

        collection_information_parsed = Collection.parse_obj(collection_information)
        if not compare_owner(collection_information_parsed, user):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED)
        
        query.delete().run(conn)

        files = r.table("files").filter(r.row["collection"] == id).run(conn)
        for file in files:
            file_information_parsed = FileInDB.parse_obj(file)
            if compare_owner(file_information_parsed, user):
                file_query = r.table("files").get(file_information_parsed.id)
                if delete_files:
                    file_query.delete().run(conn)
                    file_path = Path(FILES_PATH, file_information_parsed.file)
                    if file_path.exists():
                        file_path.unlink()
                    thumb_path = Path(THUMBS_PATH, file_information_parsed.file)
                    if thumb_path.exists():
                        thumb_path.unlink()
                else:
                    file_query.update({
                        "collection": r.literal()
                    }).run(conn)

@router.get(
    "/{id}/embed",
    response_class=HTMLResponse,
    name="embed_collection",
    description="Gets embed for a collection."
)
def embed(
    request: Request,
    id: str
):
    with get_conn() as conn:
        collection_information = r.table("collections").get(id).run(conn)
        if not collection_information:
            raise HTTPException(status.HTTP_404_NOT_FOUND)

        collection_information_parsed = Collection.parse_obj(collection_information)
        if collection_information_parsed.private:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED)

        files = FilesInDB.parse_obj(r.table("files").filter((r.row["collection"] == id) & ~r.row["private"]).order_by(r.desc("created")).run(conn))

        return templates.TemplateResponse("embed_collection.html", {
            "request": request,
            "id": id,
            "description": collection_information_parsed.description,
            "owner": collection_information_parsed.owner or "Anonymous",
            "created": collection_information_parsed.created,
            "files": files
        })
