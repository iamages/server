from argparse import ArgumentParser
from zipfile import ZipFile
from pathlib import Path
from hashlib import blake2b
import json
from csv import DictReader
from io import TextIOWrapper
from datetime import datetime
from mimetypes import guess_extension

from tqdm import tqdm

from common.db import db_images, db_collections, db_users, fs_images

from models.images import ImageInDB, ImageMetadataContainer, ImageMetadata, Lock, Thumbnail
from models.collections import Collection
from models.users import UserInDB

arg_parser = ArgumentParser(description="Tool for migrating Iamages v3 to v4 using archives.")
arg_parser.add_argument("archive_file", action="store", help="Path to the v3 archive file.")
arg_parser.add_argument("--skip-hash-check", action="store_true", help="Skip checking the archive file hash (not recommended).")
args = arg_parser.parse_args()

archive_file = Path(args.archive_file)
archive_file_hash = Path(archive_file.parent, archive_file.stem).with_suffix(".blake2b.txt")

print("[Iamages v3 to v4 Migration Tool - (C) 2022 jkelol111 et al.]")

print("0/: Checking archive version")
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
    print("1/: Migrating collections.")
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
    print("2/: Migrating images.")
    with z.open("files.csv", "r") as f:
        for file_dict in tqdm(DictReader(TextIOWrapper(f, "utf-8"))):
            image = ImageInDB(
                created_on=datetime.fromisoformat(file_dict["created"]),
                owner=file_dict["owner"] if len(file_dict["owner"]) != 0 else None,
                is_private=True if file_dict["private"] == 'True' else False,
                lock=Lock(is_locked=False),
                content_type=file_dict["mime"],
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
            fs_images.upload_from_stream_with_id(
                image.id,
                str(image.id) + guess_extension(image.content_type),
                z.open(f"files/{file_dict['file']}", "r"),
                metadata={
                    "content_type": image.content_type
                }
            )
    print("3/: Migrating users.")
    with z.open("users.csv", "r") as u:
        for user in tqdm(DictReader(TextIOWrapper(u, "utf-8"))):
            user = UserInDB(
                username=user["username"],
                created_on=datetime.fromisoformat(user["created"]).replace(microsecond=0),
                password=user["password"]
            )
            db_users.insert_one(user.dict(by_alias=True, exclude_none=True))

print("\nDone! Verify everything has been transfered over.")
    

