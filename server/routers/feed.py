from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query, status

from ..common.db import r, db_conn_mgr
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
async def latest_files(
    nsfw: bool = Query(True),
    limit: int = Body(..., ge=1, description="Limit file results."),
    start_date: Optional[datetime] = Body(None, description="Date to start returning results from.")
):
    filters = (~r.row["private"]) & (~r.row["hidden"])
    if not nsfw:
        filters = filters & (~r.row["nsfw"])
    if start_date:
        filters = filters & (r.row["created"] < start_date)
    return await r.table("files").filter(filters).order_by(r.desc("created")).limit(limit).run(db_conn_mgr.conn)

@router.get(
    "/files/popular",
    response_model=list[FileBase],
    response_model_exclude_unset=True,
    description="Get 10 most popular publicly uploaded files."
)
async def popular(
    nsfw: bool = Query(True)
):
    filters = (~r.row["private"]) & (~r.row["hidden"])
    if not nsfw:
        filters = filters & (~r.row["nsfw"])
    return await r.table("files").filter(filters).order_by(r.desc("views")).limit(10).run(db_conn_mgr.conn)

@router.get(
    "/files/random",
    response_model=FileBase,
    response_model_exclude_unset=True,
    description="Gets a random public file."
)
async def random(
    nsfw: bool = Query(False, description="Return NSFW file?")
):
    filters = (~r.row["private"]) & (~r.row["hidden"])
    if not nsfw:
        filters = filters & (~r.row["nsfw"])

    file_information = await r.table("files").filter(filters).sample(1).run(conn)

    if not file_information or file_information[0] == []:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE)

    return file_information[0]

@router.post(
    "/collections/latest",
    response_model=list[Collection],
    response_model_exclude_unset=True,
    description="Gets the latest 10 public collections."
)
async def latest_collections(
    limit: int = Body(..., ge=1, description="Limit collection results."),
    start_date: Optional[datetime] = Body(None, description="Date to start returning results from.")
):
    filters = (~r.row["private"]) & (~r.row["hidden"])
    if start_date:
        filters = filters & (r.row["created"] < start_date)
    return await r.table("collections").filter(filters).order_by(r.desc("created")).limit(limit).run(db_conn_mgr.conn)
