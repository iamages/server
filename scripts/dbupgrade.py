__version__ = "3.1.0"
__copyright__ = "© jkelol111 et al 2021-present"

from getpass import getpass
from uuid import UUID

import shortuuid
from tqdm import tqdm

from common.db import get_conn, r

BASE_FORMAT = 3
UPGRADED_FORMAT = 3

print("[Upgrade Iamages Database version '{0}'. {1}]".format(__version__, __copyright__))

print("0/3: Connecting to database.")
with get_conn(user="admin", password=getpass("Enter 'admin' password: ")) as conn:
    print("1/3: Checking database upgrade eligibility.")
    SERVER_FORMAT = r.table("internal").get(BASE_FORMAT).run(conn)
    if not SERVER_FORMAT:
        print("This script doesn't upgrade from this database version! Exiting. (expected: {})".format(BASE_FORMAT))
        exit(1)

    print("2/3: Adding new collections table.")
    r.table_create("collections").run(conn)

    print("3/3: Upgrading files table.")
    for file in tqdm(r.table("files").run(conn)):
        r.table("files").get(file["id"]).update({
            "id": shortuuid.encode(UUID(file["id"]))
        }).run(conn)

print("Done!")
