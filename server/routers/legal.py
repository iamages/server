from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..common.config import server_config
from ..common.templates import templates

router = APIRouter(
    prefix="/legal"
)

@router.get(
    "/tos",
    name="tos",
    response_class=HTMLResponse,
    include_in_schema=False
)
async def tos(request: Request):
    return templates.TemplateResponse("tos.html", {
        "request": request,
        "owner": {
            "name": server_config.iamages_server_owner,
            "contact": server_config.iamages_server_contact
        }
    })

@router.get(
    "/privacy",
    name="privacy",
    response_class=HTMLResponse,
    include_in_schema=False
)
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {
        "request": request,
        "owner": {
            "name": server_config.iamages_server_owner,
            "contact": server_config.iamages_server_contact
        }
    })

@router.get(
    "/nsfw_info",
    name="nsfw_info",
    response_class=HTMLResponse,
    include_in_schema=False
)
async def nsfw_info(request: Request):
    return templates.TemplateResponse("nsfw_info.html", {
        "request": request,
        "owner": {
            "contact": server_config.iamages_server_contact
        }
    })
