__version__ = "3.1.0"
__copyright__ = "© jkelol111 et al 2021-present"

import csv
from argparse import ArgumentParser
from datetime import datetime, timezone
from getpass import getpass
from hashlib import blake2b
from io import TextIOWrapper
from pathlib import Path
from shutil import copytree, make_archive, rmtree
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import json
from pydantic import BaseSettings, DirectoryPath

from common.config import server_config
from common.db import get_conn, r
from modals.collection import Collection
from modals.file import FileInDB
from modals.user import UserInDB

print(f"[Iamages Storage Archiving Tool version {__version__} - {__copyright__}]\n")

SUPPORTED_STORAGE_VER = 3
SUPPORTED_ARCHIVE_VER = 3

class ArchiveConfig(BaseSettings):
    iamages_archive_dir: DirectoryPath

archive_config = ArchiveConfig()

arg_parser = ArgumentParser(description="Manages Iamages storage archives.")

arg_parser.add_argument(
    "command",
    action="store",
    help="The command to run (list, archive, restore)"
)

arg_parser.add_argument(
    "data",
    action="store",
    nargs="?",
    help="The data provided to the command (optional)"
)

arg_parsed = arg_parser.parse_args()

if arg_parsed.command == "list":
    print("Found archives:")
    globbed = archive_config.iamages_archive_dir.glob("*.zip")
    archives = [file for file in globbed if file.is_file()]
    for archive in archives:
        print(f"- {archive.name}")
        with ZipFile(archive_config.iamages_archive_dir / archive) as zipped_archive:
            meta = json.loads(zipped_archive.read("meta.json"))
            print(f"  + Archive version: {meta['version']}")
            print(f"  + Archive creation date: {meta['created']}")
        hash_file = None
        if (archive_config.iamages_archive_dir / Path(archive.stem).with_suffix(".blake2b.txt")).is_file():
            hash_file = archive.stem + ".blake2b.txt"
        print(f"  + Hash file: {hash_file}")
elif arg_parsed.command == "archive":
    with TemporaryDirectory() as temp_dir:
        print("0/7: Establishing database connection.")
        with get_conn() as conn:
            if not r.table("internal").get_all(SUPPORTED_STORAGE_VER).count().eq(1).run(conn):
                raise Exception("Storage database version not supported by this script!")

            print("1/7: Exporting 'files' table.")
            with open(Path(temp_dir, "files.csv"), "w") as files_csv:
                writer = csv.DictWriter(files_csv, fieldnames=[
                    "id",
                    "description",
                    "nsfw",
                    "private",
                    "hidden",
                    "created",
                    "mime",
                    "width",
                    "height",
                    "file",
                    "owner",
                    "collection",
                    "views"
                ])
                writer.writeheader()
                writer.writerows(r.table("files").run(conn))
            
            print("2/7: Exporting 'collections' table.")
            with open(Path(temp_dir, "collections.csv"), "w") as collections_csv:
                writer = csv.DictWriter(collections_csv, fieldnames=[
                    "id",
                    "description",
                    "private",
                    "hidden",
                    "created",
                    "owner"
                ])
                writer.writeheader()
                writer.writerows(r.table("collections").run(conn))

            print("3/7: Exporting 'users' table.")
            with open(Path(temp_dir, "users.csv"), "w") as users_csv:
                writer = csv.DictWriter(users_csv, fieldnames=[
                    "username",
                    "password",
                    "created",
                    "pfp",
                    "nsfw_enabled",
                    "private",
                    "hidden"
                ])
                writer.writeheader()
                writer.writerows(r.table("users").run(conn))

        print("4/7: Copying storage directory.")
        copytree(server_config.iamages_storage_dir, temp_dir, dirs_exist_ok=True)

        created_time = datetime.now(timezone.utc)

        print("5/7: Writing archive metadata.")
        with (Path(temp_dir, "meta.json")).open("wb") as meta_file:
            meta_file.write(json.dumps({
                "version": SUPPORTED_ARCHIVE_VER,
                "created": created_time.isoformat()
            }))

        archive_basename = f"iamages-{created_time.strftime('%d%m%Y%H%M')}"

        archive_path = archive_config.iamages_archive_dir / Path(archive_basename)  

        print("6/7: Compressing archive.")
        make_archive(archive_path, "zip", temp_dir)

        print("7/7: Calculating archive hash.")
        archive_hash = blake2b()
        with open(archive_path.with_suffix(".zip"), "rb") as archive_file:
            for chunk in archive_file:
                archive_hash.update(chunk)

        with open(archive_config.iamages_archive_dir / Path(archive_basename).with_suffix(".blake2b.txt"), "w") as archive_hash_file:
            archive_hash_file.write(archive_hash.hexdigest())
elif arg_parsed.command == "restore":
    print("0/6: Checking archive integrity. (if hash is available)")

    archive_path = Path(archive_config.iamages_archive_dir, arg_parsed.data)

    archive_hash_path = archive_config.iamages_archive_dir / Path(archive_path.stem).with_suffix(".blake2b.txt")

    if archive_hash_path.is_file():
        archive_hash = blake2b()
        with open(archive_path, "rb") as archive_file:
            for chunk in archive_file:
                archive_hash.update(chunk)
        with open(archive_hash_path, "r") as hash_file:
            if not archive_hash.hexdigest() == hash_file.read():
                raise Exception(f"Hash doesn't match!\n\nExpected: {hash_file.read()}\nGot: {archive_hash.hexdigest()}")
    else:
        print("[WARN] Skipped hash verification because hash file not found! Restored data may be corrupt.")

    with ZipFile(archive_path) as zipped_archive:
        meta = json.loads(zipped_archive.read("meta.json"))

        if meta["version"] != SUPPORTED_ARCHIVE_VER:
            raise Exception(f"This archive isn't supported by this script! (expected: {SUPPORTED_ARCHIVE_VER}, got {meta['version']})")

        with get_conn("admin", getpass("Enter 'admin' password: ")) as conn:
            if 'iamages' in r.db_list().run(conn):
                erase = input("WARNING: The database 'iamages' exists already, do you want to remove it? <Y/n>: ").lower()
                if erase != "y":
                    print("Unable to proceed, stopping here.")
                    exit(1)
                r.db_drop("iamages").run(conn)

            print("1/6: Creating new 'iamages' database.")
            r.db_create("iamages").run(conn)
            r.db("iamages").grant(server_config.iamages_db_user, {
                "read": True,
                "write": True
            }).run(conn)
            r.table_create("files").run(conn)
            r.table_create("collections").run(conn)
            r.table_create("users", primary_key="username").run(conn)
            r.table_create("internal", primary_key="version").run(conn)

            print("2/6: Restoring 'files' table.")
            with zipped_archive.open("files.csv", "r") as files_csv:
                for file in csv.DictReader(TextIOWrapper(files_csv, "utf-8")):
                    file_parsed = FileInDB.parse_obj(file)
                    file_dict = file_parsed.dict(exclude_unset=True)
                    file_dict["file"] = str(file_dict["file"])
                    r.table("files").insert(file_dict).run(conn)

            print("3/6: Restoring 'collections' table.")
            with zipped_archive.open("collections.csv", "r") as collections_csv:
                for collection in csv.DictReader(TextIOWrapper(collections_csv, "utf-8")):
                    collection_parsed = Collection.parse_obj(collection)
                    r.table("collections").insert(collection_parsed.dict(exclude_unset=True)).run(conn)
            
            print("4/6: Restoring 'users' table.")
            with zipped_archive.open("users.csv", "r") as users_csv:
                for user in csv.DictReader(TextIOWrapper(users_csv, "utf-8")):
                    user_parsed = UserInDB.parse_obj(user)
                    r.table("users").insert(user_parsed.dict(exclude_unset=True)).run(conn)

            print("5/6: Writing database version metadata.")
            r.table("internal").insert({
                "version": SUPPORTED_STORAGE_VER,
                "created": r.now()
            }).run(conn)

        print("6/6: Restoring files & thumbs.")
        rmtree(server_config.iamages_storage_dir)
        server_config.iamages_storage_dir.mkdir()
        for file_in_archive in zipped_archive.namelist():
            if file_in_archive.startswith("files/") or file_in_archive.startswith("thumbs/"):
                zipped_archive.extract(file_in_archive, server_config.iamages_storage_dir)

print("\nDone!")
