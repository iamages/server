from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query, status

from ..common.db import get_conn, r
from ..modals.file import FileBase
from ..modals.collection import Collection

router = APIRouter(
    prefix="/feed",
    tags=["feed"]
)

@router.post(
    "/files/latest",
    response_model=list[FileBase],
    response_model_exclude_unset=True,
    description="Gets the latest publicly uploaded files."
)
def latest_files(
    limit: int = Body(..., ge=1, description="Limit file results."),
    start_date: Optional[datetime] = Body(None, description="Date to start returning results from.")
):
    with get_conn() as conn:
        filters = (~r.row["private"]) & (~r.row["hidden"])
        if start_date:
            filters = filters & (r.row["created"] < start_date)
        return r.table("files").filter(filters).order_by(r.desc("created")).limit(limit).run(conn)

@router.get(
    "/files/popular",
    response_model=list[FileBase],
    response_model_exclude_unset=True,
    description="Get 10 most popular publicly uploaded files."
)
def popular():
    with get_conn() as conn:
        return r.table("files").filter(
            (~r.row["private"]) & (~r.row["hidden"])
        ).order_by(r.desc("views")).limit(10).run(conn)

@router.get(
    "/files/random",
    response_model=FileBase,
    response_model_exclude_unset=True,
    description="Gets a random public file."
)
def random(
    nsfw: bool = Query(False, description="Return NSFW file?")
):
    filters = (~r.row["private"]) & (~r.row["hidden"])
    if not nsfw:
        filters = filters & (~r.row["nsfw"])

    with get_conn() as conn:
        file_information = r.table("files").filter(filters).sample(1).run(conn)

    if not file_information or file_information[0] == []:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE)

    return file_information[0]

@router.post(
    "/collections/latest",
    response_model=list[Collection],
    response_model_exclude_unset=True,
    description="Gets the latest 10 public collections."
)
def latest_collections(
    limit: int = Body(..., ge=1, description="Limit collection results."),
    start_date: Optional[datetime] = Body(None, description="Date to start returning results from.")
):
    with get_conn() as conn:
        filters = (~r.row["private"]) & (~r.row["hidden"])
        if start_date:
            filters = filters & (r.row["created"] < start_date)
        return r.table("collections").filter(filters).order_by(r.desc("created")).limit(limit).run(conn)
