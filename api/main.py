from pathlib import Path

from brotli_asgi import BrotliMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from fastapi.staticfiles import StaticFiles

from .routers import collections, images, legal, thumbnails, users

app = FastAPI(
    title="Iamages",
    description="Simple image sharing.",
    version="v4",
    openapi_url="/openapi.json",
    docs_url=None,
    redoc_url="/",
    default_response_class=ORJSONResponse
)

app.mount(
    "/private/static",
    StaticFiles(directory=Path("./api/web/static")),
    name="static"
)

app.include_router(images.router)
app.include_router(thumbnails.router)
app.include_router(collections.router)
app.include_router(users.router)
app.include_router(legal.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)
app.add_middleware(BrotliMiddleware, gzip_fallback=True)
