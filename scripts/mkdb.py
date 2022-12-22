__version__ = "4.0.0"
__copyright__ = "© jkelol111 et al 2021-present"

from getpass import getpass

from pymongo import MongoClient, TEXT

from .models.db import SUPPORTED_STORAGE_VER, DatabaseVersionModel

print(f"[Make Iamages Database {SUPPORTED_STORAGE_VER} - (C) jkelol111 et al. 2022-present]")
print("")
print("WARNING:")
print("This script presumes that you already have an admin account set up.")
print("If not, nope out below and follow the instructions at:")
print("https://docs.mongodb.com/manual/tutorial/configure-scram-client-authentication/")
print("")

conn_str = f"mongodb://\
{input('Enter DB admin username: ')}:{getpass('Enter DB admin password: ')}@{input('Enter DB URL & port: ')}\
"

client = MongoClient(conn_str)
db = client.iamages

# Create the new Iamages user.
db.command(
    "createUser",
    "iamages",
    pwd=getpass("New password for 'iamages' database user: "),
    roles=["readWrite"]
)

# Create indexes
db_images = db.images
db_images.create_index(("owner", TEXT), sparse=True)
db_collections = db.collections
db_collections.create_index(("owner", TEXT), sparse=True)

# Add database version upgrade record.
db.internal.insert_one(DatabaseVersionModel())

print("")
print("Et voila! The database and 'iamages' database user have been created.")
print("You may now start the API server.")
print("(remember, modify the IAMAGES_DB_URL environment variable!")
