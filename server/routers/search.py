from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query

from ..common.auth import auth_optional_dependency
from ..common.db import get_conn, r
from ..modals.collection import Collection
from ..modals.file import FileBase
from ..modals.user import UserBase

router = APIRouter(
    prefix="/search",
    tags=["search"]
)

@router.post(
    "/files",
    response_model=list[FileBase],
    response_model_exclude_unset=True,
    description="Searches for files."
)
def search_files(
    description: str = Body(..., description="Description to search for."),
    limit: Optional[int] = Body(None, ge=1, description="Limit search results."),
    start_date: Optional[datetime] = Body(None, description="Date to start searching from."),
    username: Optional[str] = Query(None, description="Username to search files in."),
    user: Optional[UserBase] = Depends(auth_optional_dependency),
):
    query = r.table("files")
    filters = r.row["description"].match(f"(?i){description}")

    if username:
        filters  = filters & (r.row["owner"] == username)
        if not user:
            filters = filters & (~r.row["private"]) & (~r.row["hidden"])

    if start_date:
        filters = filters & (r.row["created"] < start_date)

    query = query.filter(filters).order_by(r.desc("created"))

    if limit:
        query = query.limit(limit)

    with get_conn() as conn:
        return query.run(conn)

@router.post(
    "/collections",
    response_model=list[Collection],
    response_model_exclude_unset=True,
    description="Searches for collections."
)
def search_collections(
    description: str = Body(..., description="Description to search for."),
    limit: Optional[int] = Body(None, ge=1, description="Limit search results."),
    start_date: Optional[datetime] = Body(None, description="Date to start searching from."),
    username: Optional[str] = Query(None, description="Username to search files in."),
    user: Optional[UserBase] = Depends(auth_optional_dependency),
):
    query = r.table("collections")
    filters = r.row["description"].match(f"(?i){description}")

    if username:
        filters  = filters & (r.row["owner"] == username)
        if not user:
            filters = filters & (~r.row["private"]) & (~r.row["hidden"])

    if start_date:
        filters = filters & (r.row["created"] < start_date)

    query = query.filter(filters).order_by(r.desc("created"))

    if limit:
        query = query.limit(limit)

    with get_conn() as conn:
        return query.run(conn)

@router.post(
    "/users",
    response_model=list[UserBase],
    response_model_exclude_unset=True,
    description="Searches for users."
)
def search_users(
    username: str = Body(..., description="Username to search for."),
    limit: Optional[int] = Body(None, ge=1, description="Limit search results."),
    start_date: Optional[datetime] = Body(None, description="Date to start searching from.")
):
    query = r.table("users")
    filters = r.row["username"].match(f"(?i){username}")

    if start_date:
        filters = filters & (r.row["created"] < start_date)

    query = query.filter(filters).order_by(r.desc("created"))

    if limit:
        query = query.limit(limit)

    with get_conn() as conn:
        return query.run(conn)
