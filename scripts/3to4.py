import json
import re
from argparse import ArgumentParser
from csv import DictReader
from datetime import datetime
from hashlib import blake2b
from io import TextIOWrapper
from mimetypes import guess_extension
from pathlib import Path
from zipfile import ZipFile
from shutil import rmtree, copyfileobj

from common.db import db_collections, db_images, db_users
from common.paths import IMAGES_PATH, THUMBNAILS_PATH
from models.collections import Collection
from models.images import (ImageInDB, ImageMetadata, ImageMetadataContainer,
                           Lock, Thumbnail, File)
from models.users import UserInDB
from tqdm import tqdm

arg_parser = ArgumentParser(description="Tool for migrating Iamages v3 to v4 using archives.")
arg_parser.add_argument("archive_file", action="store", help="Path to the v3 archive file.")
arg_parser.add_argument("--skip-hash-check", action="store_true", help="Skip checking the archive file hash (not recommended).")
args = arg_parser.parse_args()

archive_file = Path(args.archive_file)
archive_file_hash = Path(archive_file.parent, archive_file.stem).with_suffix(".blake2b.txt")

print("[Iamages v3 to v4 Migration Tool - (C) 2022 jkelol111 et al.]")

print("0/3: Checking archive version")
if not args.skip_hash_check:
    hash = blake2b()
    with open(archive_file, "rb") as f:
        for chunk in f:
            hash.update(chunk)
    with open(archive_file_hash, "r") as f:
        if hash.hexdigest() != f.read():
            raise Exception(f"Archive hash doesn't match!\n\nExpected: {f.read()}\nGot: {hash.hexdigest()}")
else:
    print("[WARN] Archive hash checking is highly recommended. Omit the --skip-hash-check argument to do this.")

with ZipFile(archive_file) as z:
    with z.open("meta.json") as metaf:
        meta = json.load(metaf)
        if meta["version"] != 3:
            raise Exception(f"Archive file version is not supported.\n\nExpected: 3\nGot: {meta['version']}")

    rmtree(IMAGES_PATH, ignore_errors=True)
    IMAGES_PATH.mkdir()
    rmtree(THUMBNAILS_PATH)

    print("1/3: Migrating collections.")
    collections_map = {}
    with z.open("collections.csv", "r") as c:
        for collection_dict in tqdm(DictReader(TextIOWrapper(c, "utf-8"))):
            collection = Collection(
                owner=collection_dict["owner"],
                is_private=collection_dict["private"],
                description=collection_dict["description"]
            )
            collections_map[collection_dict["id"]] = collection.id
            db_collections.insert_one(collection.dict(by_alias=True, exclude_none=True, exclude={"created_on"}))
    excluded_users = []
    print("2/3: Migrating users")
    with z.open("users.csv", "r") as u:
        for user in tqdm(DictReader(TextIOWrapper(u, "utf-8"))):
            if re.search(" +", user["username"]):
                excluded_users.append(user["username"])
                continue
            user = UserInDB(
                username=user["username"],
                created_on=datetime.fromisoformat(user["created"]).replace(microsecond=0),
                password=user["password"]
            )
            db_users.insert_one(user.dict(by_alias=True, exclude_none=True))
    print("3/3: Migrating images.")
    with z.open("files.csv", "r") as f:
        for file_dict in tqdm(DictReader(TextIOWrapper(f, "utf-8"))):
            if file_dict["owner"] == "" or file_dict["owner"] in excluded_users:
                continue
            image = ImageInDB(
                created_on=datetime.fromisoformat(file_dict["created"]),
                owner=file_dict["owner"],
                is_private=True if file_dict["private"] == 'True' else False,
                lock=Lock(is_locked=False),
                file=File(
                    content_type=file_dict["mime"],
                    type_extension=guess_extension(file_dict["mime"])
                ),
                thumbnail=Thumbnail(),
                metadata=ImageMetadataContainer(
                    data=ImageMetadata(
                        description="No description provided." if len(file_dict["description"]) == 0 else file_dict["description"],
                        width=int(file_dict["width"]),
                        height=int(file_dict["height"])
                    )
                )
            )
            if file_dict["collection"] in collections_map:
                image.collections = [collections_map[file_dict["collection"]]]
            db_images.insert_one(
                image.dict(
                    by_alias=True,
                    exclude_none=True,
                    exclude={
                        "created_on": ...,
                        "lock": {"upgradable": ...}
                    }
                )
            )
            with (
                z.open(f"files/{file_dict['file']}", "r") as old_image,
                open(IMAGES_PATH / f"{image.id}{image.file.type_extension}", "wb") as new_image
            ):
                copyfileobj(old_image, new_image)
print("\nDone! Verify everything has been transfered over.")
    

