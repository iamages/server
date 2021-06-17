import subprocess
from argparse import ArgumentParser
from datetime import datetime, timezone
from hashlib import blake2b
from pathlib import Path
from shutil import copytree, make_archive
from tempfile import TemporaryDirectory

import orjson
from pydantic import BaseSettings, DirectoryPath

from common import server_config

SUPPORTED_ARCHIVE_DIR = 3


class ArchiveConfig(BaseSettings):
    archive_dir: DirectoryPath
    archive_ver: int = SUPPORTED_ARCHIVE_DIR

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
    globbed = archive_config.archive_dir.glob("*.iamagesbak.zip")
    archives = [file for file in globbed if file.is_file()]
    for archive in archives:
        print(f"- {archive.name}")
        hash_file = None
        if (archive_config.archive_dir / Path(archive.stem).with_suffix(".iamagesbak.blake2b.txt")).is_file():
            hash_file = archive.stem + ".blake2b.txt"
        print(f"    + Hash file: {hash_file}")
elif arg_parsed.command == "archive":
    with TemporaryDirectory() as temp_dir:
        subprocess.run([
            "rethinkdb",
            "dump",
            "--connect", f"{server_config.db_host}:{server_config.db_port}",
            "--export", "iamages",
            "--file", str(Path(temp_dir).with_suffix("db.tar.gz"))
        ])

        copytree(server_config.storage_dir, temp_dir, dirs_exist_ok=True)

        created_time = datetime.now(timezone.utc)

        with (Path(temp_dir) / Path("meta.json")).open("wb") as meta_file:
            meta_file.write(orjson.dumps({
                "version": archive_config.archive_ver,
                "created": created_time
            }))

        archive_basename = f"iamages-{created_time.strftime('%d%m%Y%H%M')}.iamagesbak"

        archive_path = archive_config.archive_dir / Path(archive_basename)

        make_archive(archive_path, "zip", temp_dir)

        archive_hash = blake2b()
        with archive_path.open("rb") as archive_file:
            for chunk in archive_file:
                archive_hash.update(chunk)

        archive_hash_path = archive_config.archive_dir / Path(archive_basename).with_suffix(".blake2b.txt")
        with archive_hash_path.open("w") as archive_hash_file:
            archive_hash_file.write(archive_hash.hexdigest)
elif arg_parsed.command == "restore":
    pass
    # TODO: Restore backups
    # Blocked by RethinkDB's dump/import commands being broken on Python 3
