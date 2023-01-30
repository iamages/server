__version__ = "4.0.0"
__copyright__ = "© jkelol111 et al 2023-present"

from getpass import getpass
from urllib.parse import quote

from pymongo import MongoClient, TEXT, DESCENDING

from models.db import DatabaseVersionModel

print(f"[Make Iamages Database v{__version__} - {__copyright__}]")
print("")
print("WARNING:")
print("This script presumes that you already have an admin account set up.")
print("If not, nope out below and follow the instructions at:")
print("https://docs.mongodb.com/manual/tutorial/configure-scram-client-authentication/")
print("")

conn_str = f"mongodb://\
{quote(input('Enter DB admin username: '))}:{quote(getpass('Enter DB admin password: '))}@{input('Enter DB URL & port (host:port): ')}\
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
db.images.create_index([("owner", TEXT), ("metadata.data.description", TEXT)], sparse=True)
db.images.create_index([("collections", DESCENDING)], sparse=True)

db.collections.create_index([("owner", TEXT), ("description", TEXT)])

db.users.create_index([("email", TEXT)], sparse=True)

db.password_resets.create_index("created_on", expireAfterSeconds=900)

# Add database version upgrade record.
db.internal.insert_one(DatabaseVersionModel().dict())

print("")
print("Et voila! The database and 'iamages' database user have been created.")
print("You may now start the API server.")
print("(remember, modify the IAMAGES_DB_URL environment variable!")
