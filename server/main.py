from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image

from .routers import collection, feed, file, legal, root, search, user
from .common.db import db_conn_mgr

Image.MAX_IMAGE_PIXELS = None

tags_metadata = [
    {
        "name": "feed",
        "description": "Public file lists."
    },
    {
        "name": "file",
        "description": "Operations with files.",
    },
    {
        "name": "collection",
        "description": "Operations with collections."
    },
    {
        "name": "user",
        "description": "Operations with users.",
    },
    {
        "name": "search",
        "description": "Search for objects."
    }
]

app = FastAPI(
    title="Iamages",
    description="Simple image sharing server.",
    version="v3",
    openapi_url="/openapi.json",
    docs_url=None,
    redoc_url="/",
    root_path="/iamages/api/v3",
    openapi_tags=tags_metadata
)

@app.on_event("startup")
async def startup():
    await db_conn_mgr.connect()

@app.on_event("shutdown")
async def shutdown():
    await db_conn_mgr.close()

app.mount("/private/static", StaticFiles(directory=Path("./server/web/static")), name="static")
app.include_router(feed.router)
app.include_router(file.router)
app.include_router(collection.router)
app.include_router(user.router)
app.include_router(search.router)
app.include_router(legal.router)
app.include_router(root.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)
app.add_middleware(GZipMiddleware)
