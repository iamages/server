from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..common.settings import api_settings
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
            "name": api_settings.iamages_server_owner,
            "contact": api_settings.iamages_server_contact
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
            "name": api_settings.iamages_server_owner,
            "contact": api_settings.iamages_server_contact
        }
    })
