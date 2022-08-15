from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket
from .settings import api_settings

db = AsyncIOMotorClient(api_settings.db_url, tz_aware=True).iamages
db_images = db.images
fs_images = AsyncIOMotorGridFSBucket(db, bucket_name="fs_images")
fs_thumbnails = AsyncIOMotorGridFSBucket(db, bucket_name="fs_thumbnails")

async def yield_grid_file(grid_out):
    while True:
        chunk = await grid_out.readchunk()
        if not chunk:
            break
        yield chunk
