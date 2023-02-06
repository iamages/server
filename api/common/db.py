from pymongo import MongoClient
from .settings import api_settings

db = MongoClient(
    api_settings.db_url,
    tz_aware=True,
    uuidRepresentation="standard"
).iamages
db_images = db.images
db_collections = db.collections
db_users = db.users
