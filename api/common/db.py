from pymongo import MongoClient
from gridfs import GridFSBucket, GridOut
from .settings import api_settings

db = MongoClient(
    api_settings.db_url,
    tz_aware=True,
    uuidRepresentation="standard"
).iamages
db_images = db.images
db_collections = db.collections
db_users = db.users
fs_images = GridFSBucket(db, bucket_name="fs_images")
fs_thumbnails = GridFSBucket(db, bucket_name="fs_thumbnails")

def yield_grid_file(grid_out: GridOut):
    while True:
        chunk = grid_out.readchunk()
        if not chunk:
            break
        yield chunk
