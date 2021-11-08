from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query, status

from ..common.db import get_conn, r
from ..modals.file import FileBase

router = APIRouter(
    prefix="/feed",
    tags=["feed"]
)

@router.post(
    "/latest",
    response_model=list[FileBase],
    description="Gets the latest 10 publicly uploaded files."
)
def latest(
    limit: int = Body(..., ge=1, description="Limit file results."),
    start_date: Optional[datetime] = Body(None, description="Date to start returning results from.")
):
    with get_conn() as conn:
        filters = (~r.row["private"]) & (~r.row["hidden"])
        if start_date:
            filters = filters & (r.row["created"] < start_date)
        return r.table("files").filter(filters).order_by(r.desc("created")).limit(limit).run(conn)

@router.post(
    "/popular",
    response_model=list[FileBase],
    description="Get the most popular publicly uploaded files."
)
def popular(
    limit: int = Body(..., ge=1, description="Limit file results."),
    start_id: Optional[str] = Body(None, description="File ID to start returning results from.")
):
    with get_conn() as conn:
        query = r.table("files").filter(
            (~r.row["private"]) & (~r.row["hidden"])
        ).order_by(r.desc("views"))

        if start_id:
            query = query.slice(start_id)

        return query.limit(limit).run(conn)

@router.get(
    "/random",
    response_model=FileBase,
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
