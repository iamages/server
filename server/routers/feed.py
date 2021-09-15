from fastapi import APIRouter, HTTPException, Query, status

from ..common.db import get_conn, r
from ..modals.file import FileBase

router = APIRouter(
    prefix="/feed",
    tags=["feed"]
)

@router.get(
    "/latest",
    response_model=list[FileBase],
    description="Gets the latest 10 publicly uploaded files."
)
def latest():
    with get_conn() as conn:
        return r.table("files").filter(
            (~r.row["private"]) & (~r.row["hidden"])
        ).order_by(r.desc("created")).limit(10).run(conn)

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
