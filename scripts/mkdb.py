__version__ = "3.1.0"
__copyright__ = "© jkelol111 et al 2021-present"

from getpass import getpass

from common.config import server_config
from common.db import get_conn, r

SUPPORTED_STORAGE_VER = 3

print("[Make Iamages Database version '{0}'. {1}]".format(__version__, __copyright__))

conn = get_conn("admin", getpass("Enter 'admin' password: "), "iamages")

print("- Creating new database user 'iamages' & password 'iamages'.")
r.db("rethinkdb").table("users").insert({
    "id": server_config.iamages_db_user,
    "password": server_config.iamages_db_pwd
}).run(conn)

if 'iamages' in r.db_list().run(conn):
    erase = input("WARNING: The database 'iamages' exists already, do you want to remove it? <Y/n>: ").lower()
    if erase != "y":
        print("Unable to proceed, stopping here.")
        exit(1)
    r.db_drop("iamages").run(conn)

print("- Creating new 'iamages' database.")
r.db_create("iamages").run(conn)

print("- Granting 'iamages' user access to new 'iamages' database.")
r.db("iamages").grant(server_config.iamages_db_user, {
    "read": True,
    "write": True
}).run(conn)

print("- Creating tables in database.")
r.table_create("files").run(conn)
# r.table_create("collections").run(conn)
r.table_create("users", primary_key="username").run(conn)
r.table_create("internal", primary_key="version").run(conn)

print("- Writing database information.")
r.table("internal").insert({
    "version": SUPPORTED_STORAGE_VER,
    "created": r.now()
}).run(conn)

conn.close()

print("Done!")
