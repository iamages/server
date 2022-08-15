__version__ = "4.0.0"
__copyright__ = "© jkelol111 et al 2021-present"

from getpass import getpass

from pymongo import MongoClient

SUPPORTED_STORAGE_VER = 4

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

print("")
print("Et voila! The database and 'iamages' database user have been created.")
print("You may now start the API server.")
print("(remember, modify the IAMAGES_DB_URL environment variable!")
