from uuid import UUID

import shortuuid
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()

@router.get(
    "/ping",
    response_class=PlainTextResponse,
    description="Check if the API is alive."
)
def ping():
    return "pong!"

@router.get(
    "/compat2/{uuid}",
    response_class=PlainTextResponse,
    description="Generate a ShortUUID from an existing UUID to find the new file `id`."
)
def compat2(uuid: UUID):
    return shortuuid.encode(uuid)
