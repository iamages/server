from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse
from fastapi.staticfiles import StaticFiles

from .routers import everyone, file, user

tags_metadata = [
    {
        "name": "everyone",
        "description": "General operations.",
    },
    {
        "name": "file",
        "description": "Operations with files.",
    },
    {
        "name": "user",
        "description": "Operations with users.",
    }
]

app = FastAPI(
    title="Iamages",
    description="Simple image sharing server.",
    version="2",
    openapi_url="/openapi.json",
    docs_url=None,
    redoc_url="/",
    root_path="/iamages/api/v2",
    openapi_tags=tags_metadata,
    default_response_class=ORJSONResponse
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)
app.add_middleware(GZipMiddleware)

app.mount("/private/static", StaticFiles(directory=Path("./server/web/static")), name="static")
app.include_router(everyone.router)
app.include_router(file.router)
app.include_router(user.router)
