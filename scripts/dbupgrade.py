__version__ = "3.2.0"
__copyright__ = "© jkelol111 et al 2021-present"

from getpass import getpass
from tqdm import tqdm

from common.db import get_conn, r

BASE_FORMAT = 3
UPGRADED_FORMAT = 3

print("[Upgrade Iamages Database version '{0}'. {1}]".format(__version__, __copyright__))

print("1/2: Connecting to database.")
with get_conn(user="admin", password=getpass("Enter 'admin' password: ")) as conn:
    print("1/2: Checking database upgrade eligibility.")
    SERVER_FORMAT = r.table("internal").get(BASE_FORMAT).run(conn)
    if not SERVER_FORMAT:
        print("This script doesn't upgrade from this database version! Exiting. (expected: {})".format(BASE_FORMAT))
        exit(1)

    print("2/2: Upgrading users table.")
    for user in tqdm(r.table("users").run(conn)):
        r.table("users").get(user["username"]).update({
            "nsfw_enabled": False
        }).run(conn)

print("Done!")
