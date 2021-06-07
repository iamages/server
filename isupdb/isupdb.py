__version__ = "3.0.0"
__copyright__ = "© jkelol111 et al 2021-present"

import pathlib
import sqlite3
import rethinkdb
import orjson
import datetime
import uuid
import mimetypes
import shutil
from tqdm import tqdm

print("[Upgrade Iamages Database version '{0}'. {1}]".format(__version__, __copyright__))

BASE_FORMAT = 2
UPGRADED_FORMAT = 3

print("1/2: Load the server configuration file.")
server_config = {}
CONFIG_PATH = pathlib.Path("./servercfg.json")
if not CONFIG_PATH.exists():
    print("Could not find server config file!")
    exit(1)

with open(CONFIG_PATH, "r") as config_file:
    server_config = orjson.loads(config_file.read())

if not server_config["files"]["storage"]["format"] == BASE_FORMAT:
    print("This script doesn't upgrade from this database version! Exiting. (got: {}, expected: {})".format(server_config["files"]["storage"]["format"], BASE_FORMAT))
    exit(1)

print("2/2: Migrating to new database.")
FILESDB_PATH = pathlib.Path(server_config["files"]["storage"]["directory"], "iamages.db")

if not FILESDB_PATH.exists():
    print("Database doesn't exist! Exiting.")
    exit(1)

storedb_connection = sqlite3.connect(FILESDB_PATH)
storedb_cursor = storedb_connection.cursor()

r = rethinkdb.RethinkDB()
conn = r.connect(user="admin", db="iamages")

print("- Creating new database user 'iamages' & password 'iamages'.")
r.db("rethinkdb").table("users").insert({
    "id": "iamages",
    "password": "iamages"
}).run(conn)

print("- Checking for and deleting existing 'iamages' database.")

if 'iamages' in r.db_list().run(conn):
    erase = input("WARNING: The database 'iamages' exists already, do you want to remove it? <Y/n>: ").lower()
    if erase != "y":
        print("Unable to proceed, stopping here.")
        exit(1)
    r.db_drop("iamages").run(conn)

print("- Creating new 'iamages' database.")
r.db_create("iamages").run(conn)

print("- Granting 'iamages' user access to new 'iamages' database.")
r.db("iamages").grant("iamages", {
    "read": True,
    "write": True
}).run(conn)

print("- Creating tables in database.")
r.table_create("files").run(conn)
r.table_create("users", primary_key="username").run(conn)
r.table_create("internal", primary_key="version").run(conn)

print("- Migrating 'Files' table.")
file_id_map = {}

for file in tqdm(storedb_cursor.execute("SELECT * FROM Files").fetchall()):
    created_datetime = datetime.datetime.strptime(file[10], "%Y-%m-%d %H:%M:%S")
    file_id_map[str(file[0])] = str(uuid.uuid4())
    new_file = {
        "id": file_id_map[str(file[0])],
        "description": file[2],
        "nsfw": bool(file[3]),
        "private": bool(file[4]),
        "created": r.time(created_datetime.year, created_datetime.month, created_datetime.day, created_datetime.hour, created_datetime.minute, created_datetime.second, "Z"),
        "hidden": bool(file[11])
    }

    if file[1]:
        new_file["file"] = file[1]
    if file[5]:
        new_file["mime"] = file[5]
    if file[6]:
        new_file["width"] = file[6]
    if file[7]:
        new_file["height"] = file[7]

    if file[9]:
        linked_file_information = storedb_cursor.execute("SELECT FileName, FileMime, FileWidth, FileHeight FROM Files WHERE FileID = ?", (file[9],)).fetchone()
        linked_file_path = pathlib.Path(server_config["files"]["storage"]["directory"], "files", linked_file_information[0])
        new_file_name = uuid.uuid4().hex + mimetypes.guess_extension(linked_file_information[1])
        shutil.copy(linked_file_path, pathlib.Path(server_config["files"]["storage"]["directory"], "files", new_file_name))

        new_file["file"] = new_file_name
        new_file["mime"] = linked_file_information[1]
        new_file["width"] = linked_file_information[2]
        new_file["height"] = linked_file_information[3]
    elif not file[5] and not file[9]:
        continue
    
    r.table("files").insert(new_file).run(conn)

print("- Migrating 'Users' table.")
user_id_map = {}
for user in tqdm(storedb_cursor.execute("SELECT * FROM Users").fetchall()):
    created_datetime = datetime.datetime.strptime(user[4], "%Y-%m-%d %H:%M:%S")
    user_id_map[str(user[0])] = user[1]
    new_user = {
        "username": user[1],
        "password": user[2].replace("b'", "").replace("'", ""),
        "created": r.time(created_datetime.year, created_datetime.month, created_datetime.day, created_datetime.hour, created_datetime.minute, created_datetime.second, "Z")
    }
    r.table("users").insert(new_user).run(conn)

print("- Migrating 'Files_Users' table.")
for file_user in tqdm(storedb_cursor.execute("SELECT * FROM Files_Users").fetchall()):
    if r.table("files").get(file_id_map[str(file_user[0])]).run(conn):
        r.table("files").get(file_id_map[str(file_user[0])]).update({
            "owner": user_id_map[str(file_user[1])]
        }).run(conn)

print("- Writing database information")
r.table("internal").insert({
    "version": 3,
    "created": r.now()
}).run(conn)

storedb_connection.close()
conn.close()

print("NOTE: servercfg.json has been deprecated, please use a startup script using environment variables to provide the server's configuration.")
print("NOTE: please refer to README.md for more information.")

print("Done!")