__version__ = "4.0.0"
__copyright__ = "© jkelol111 et al 2023-present"

from getpass import getpass
from shutil import rmtree
from urllib.parse import quote

from common.settings import api_settings
from pymongo import MongoClient

print(f"[Drop Iamages Database v{__version__} - {__copyright__}]")

conn_str = f"mongodb://\
{quote(input('Enter DB admin username: '))}:{quote(getpass('Enter DB admin password: '))}@{input('Enter DB URL & port (host:port): ')}\
"
client = MongoClient(conn_str)

print("WARNING: All data in the 'iamages' database will be deleted! Unless you have a backup, there is no way back.")
match input("Continue? <y/n> ").lower():
    case "y":
        client.iamages.command("dropUser", "iamages")
        client.drop_database("iamages")
        print("Poof, it's gone.")
    case "n" | _:
        print("Cancelled database drop.")

match input("Wipe storage directory as well? <y/n> ").lower():
    case "y":
        rmtree(api_settings.storage_dir)
        api_settings.storage_dir.mkdir()
        print("Kazaam, that's also gone.")
    case "n":
        print("Storage directory not wiped.")
