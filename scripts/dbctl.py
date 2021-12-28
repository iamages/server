__version__ = "3.1.0"
__copyright__ = "© jkelol111 et al 2021-present"

from argparse import ArgumentParser
from getpass import getpass
from pathlib import Path
from pprint import pprint

from common.config import server_config
from common.db import get_conn, r
from common.paths import FILES_PATH, THUMBS_PATH

arg_parser = ArgumentParser(description="Manage the Iamages database.")
arg_parser.add_argument(
    "command",
    action="store",
    help="The command to run (chupwd, getfile, getuser)"
)
arg_parser.add_argument(
    "data",
    action="store",
    nargs="?",
    help="The data provided to the command (optional)"
)

arg_parsed = arg_parser.parse_args()

with get_conn(user=server_config.iamages_db_user, password=server_config.iamages_db_pwd) as conn:
    if arg_parsed.command == "chupwd":
        new_password = getpass(f"Enter a new password for {server_config.iamages_db_user}: ")
        new_password_confirm = getpass("Enter the new password again: ")
        if new_password != new_password_confirm:
            raise Exception("Password mismatch!")
        r.db("rethinkdb").table("users").get(server_config.iamages_db_user).update({
            "password": new_password
        }).run(conn)
        print(f"Changed the password for database user '{server_config.iamages_db_user}'.")
    elif arg_parsed.command == "getfile":
        pprint(r.table("files").get(arg_parsed.data).run(conn))
    elif arg_parsed.command == "getuser":
        pprint(r.table("users").get(arg_parsed.data).run(conn))
    elif arg_parsed.command == "getcollection":
        pprint(r.table("collections").get(arg_parsed.data).run(conn))
    elif arg_parsed.command == "deletefile":
        query = r.table("files").get(arg_parsed.data)
        file_information = query.run(conn)
        if not file_information:
            print("File doesn't exist!")
            exit(1)
        file = Path(FILES_PATH, file_information["file"])
        if file.exists():
            file.unlink()
        thumb = Path(THUMBS_PATH, file_information["file"])
        if thumb.exists():
            thumb.unlink()
        query.delete().run(conn)
    else:
        print("Command doesn't exist!")
