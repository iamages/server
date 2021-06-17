from argparse import ArgumentParser
from getpass import getpass
from pprint import pprint

from rethinkdb import RethinkDB

from common import server_config

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

r = RethinkDB()
conn = r.connect(
    host=server_config.db_host,
    port=server_config.db_port,
    user="admin",
    password=getpass("Enter admin password: "),
    db="iamages"
)

if arg_parsed.command == "chupwd":
    new_password = getpass("Enter a new password for the Iamages database: ")
    new_password_confirm = getpass("Enter the new password again: ")
    if new_password != new_password_confirm:
        raise Exception("Password mismatch!")
    r.db("rethinkdb").table("users").get(server_config.db_user).update({
        "password": new_password
    }).run(conn)
    print(f"Changed the password for database user '{server_config.db_user}'.")
elif arg_parsed.command == "getfile":
    pprint(r.table("files").get(arg_parsed.data).run(conn))
elif arg_parsed.command == "getuser":
    pprint(r.table("users").get(arg_parsed.data).run(conn))
else:
    print("Command doesn't exist!")

conn.close()
