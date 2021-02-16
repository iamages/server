__version__ = "2.1.0"
__copyright__ = "© jkelol111 et al 2020-present"

import os
import json
import sqlite3

SUPPORTED_FORMAT = 2

print("[Make Iamages Database version '{0}'. {1}]".format(__version__, __copyright__))

print("0/3: Load the server configuration file.")
server_config = json.load(open("servercfg.json", "r"))

print("1/3: Finding existing database and deleting it.")
FILESDB_PATH = os.path.join(os.getcwd(), server_config["files"]["storage"]["directory"], "iamages.db")
if os.path.isfile(FILESDB_PATH):
    os.remove(FILESDB_PATH)

if not os.path.isdir(server_config["files"]["storage"]["directory"]):
    os.makedirs(server_config["files"]["storage"]["directory"])

print("2/3: Create the new database.")
storedb_connection = sqlite3.connect(FILESDB_PATH, )
storedb_cursor = storedb_connection.cursor()

storedb_cursor.execute("PRAGMA journal_mode=WAL")

print("3/3: Execute database creation.")
with open("iamagesdb.sql", "r") as sqlscript:
    storedb_cursor.executescript(sqlscript.read())

server_config["files"]["storage"]["format"] = SUPPORTED_FORMAT

json.dump(server_config, open("servercfg.json", "w"))

print("Done!")