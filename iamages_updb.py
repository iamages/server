__version__ = "2.1.0"
__copyright__ = "© jkelol111 et al 2020-present"

import os
import json
import sqlite3

print("[Upgrade Iamages Database version '{0}'. {1}]".format(__version__, __copyright__))

BASE_FORMAT = 1
UPGRADED_FORMAT = 2

print("0/3: Load the server configuration file.")
server_config = json.load(open("servercfg.json", "r"))

if not server_config["files"]["storage"]["format"] == BASE_FORMAT:
    print("This script doesn't upgrade from this database version! Exiting. (got: {}, expected: {})".format(server_config["files"]["storage"]["format"], BASE_FORMAT))
    exit(1)

print("1/3: Analysing existing database.")
FILESDB_PATH = os.path.join(server_config["files"]["storage"]["directory"], "iamages.db")

if not os.path.isfile(FILESDB_PATH):
    print("Database doesn't exist! Exiting.")
    exit(1)

storedb_connection = sqlite3.connect(FILESDB_PATH)
storedb_cursor = storedb_connection.cursor()

files_table_columns = storedb_cursor.execute("PRAGMA table_info('Files')").fetchall()

FilesExcludeSearch_found = False

for files_table_column in files_table_columns:
    if files_table_column[1] == "FileExcludeSearch":
        FilesExcludeSearch_found = True
        print("FilesExcludeSearch column found. No change required.")
        break

if not FilesExcludeSearch_found:
    print("2/3: Performing database upgrade.")
    storedb_cursor.execute("ALTER TABLE Files ADD FileExcludeSearch INTEGER")
    FileIDs = storedb_cursor.execute("SELECT FileID FROM Files").fetchall()
    for FileID in FileIDs:
        storedb_cursor.execute("UPDATE Files SET FileExcludeSearch = ? WHERE FileID = ?", (False, FileID[0]))

storedb_connection.commit()
storedb_connection.close()

print("3/3: Updating server configuration.")
server_config["files"]["storage"]["format"] = UPGRADED_FORMAT
json.dump(server_config, open("servercfg.json", "w"))

print("Done!")