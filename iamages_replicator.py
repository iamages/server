__version__ = "2.2.0"
__copyright__ = "© jkelol111 et al 2021-present"

import argparse
import os
import shutil
import sqlite3
import csv
import json
import hashlib
import datetime
import tempfile
from tqdm import tqdm

print("[Iamages Storage Replicator version '{0}'. {1}]".format(__version__, __copyright__))

SUPPORTED_FORMAT = 2

print("0/?: Load the server configuration file.")
server_config = json.load(open("servercfg.json", "r"))

print("0/?: Load the replicator configuration file.")
replicator_config = json.load(open("replicatorcfg.json", "r"))

print("0/?: Load previous replicated archives list.")
archives = {}
archives_filepath = os.path.join(replicator_config["directory"], "archives.json")
if os.path.isfile(archives_filepath):
    archives = json.load(open(archives_filepath, "r"))

print("")

CMD_PARSER = argparse.ArgumentParser(
    description='Back up or restore a replicated Iamages archive.'
)

CMD_PARSER.add_argument(
    'command',
    action='store',
    help='The command to run (archive, restore, delete, list)')

CMD_PARSER.add_argument(
    'archive_name',
    action='store',
    nargs="?",
    help='The name of the replicated archive (for use with restore and delete command).')

CMD_PARSED = CMD_PARSER.parse_args()

def delete_archive(archive):
    if not archive in archives:
        raise FileNotFoundError("Archive {} not found!".format(archive))

    os.remove(os.path.join(replicator_config["directory"], archive + ".zip"))
    if archives[archive]["has_hash"]:
        os.remove(os.path.join(replicator_config["directory"], archive + ".blake2b.txt"))
    archives.pop(archive)
    json.dump(archives, open(archives_filepath, "w"))

if CMD_PARSED.command == "archive":
    if not server_config["files"]["storage"]["format"] == SUPPORTED_FORMAT:
        print(f'Current storage format is not supported. (expected: {SUPPORTED_FORMAT}, got: {server_config["files"]["format"]})')
        exit(1)
    with tempfile.TemporaryDirectory() as tmp:
        print("1/5: Copying current storage directory to temporary directory.")
        shutil.copytree(server_config["files"]["storage"]["directory"], tmp, dirs_exist_ok=True, ignore=shutil.ignore_patterns("replicated"))

        print("2/5: Establish connection to Iamages database.")
        conn = sqlite3.connect(os.path.join(tmp, "iamages.db"))
        cur = conn.cursor()

        print("3/5: Exporting Files table to CSV.")
        with open(os.path.join(tmp, "Files.csv"), "w") as csv_files:
            writer = csv.writer(csv_files)
            writer.writerow(["FileID", "FileName", "FileDescription", "FileNSFW", "FilePrivate", "FileMime", "FileWidth", "FileHeight", "FileHash", "FileLink", "FileCreatedDate", "FileExcludeSearch"])
            pbar = tqdm(cur.execute("SELECT * FROM Files").fetchall())
            for row in pbar:
                writer.writerow(row)

        print("3/5: Exporting Files_Users table to CSV.")
        with open(os.path.join(tmp, "Files_Users.csv"), "w") as csv_files_users:
            writer = csv.writer(csv_files_users)
            writer.writerow(["FileID", "UserID"])
            pbar = tqdm(cur.execute("SELECT * FROM Files_Users").fetchall())
            for row in pbar:
                writer.writerow(row)

        print("4/5: Exporting Users table to CSV.")
        with open(os.path.join(tmp, "Users.csv"), "w") as csv_users:
            writer = csv.writer(csv_users)
            writer.writerow(["UserID", "UserName", "UserPassword", "UserBiography", "UserCreatedDate"])
            pbar = tqdm(cur.execute("SELECT * FROM Users").fetchall())
            for row in pbar:
                writer.writerow(row)

        conn.close()
        os.remove(os.path.join(tmp, "iamages.db"))

        print("5/5: Saving as replicated archive.")

        current_datetime = datetime.datetime.now()
        substitute_datetimes = {
            "year": current_datetime.strftime("%Y"),
            "month": current_datetime.strftime("%m"),
            "day": current_datetime.strftime("%d"),
            "hour": current_datetime.strftime("%H"),
            "minute": current_datetime.strftime("%M"),
            "second": current_datetime.strftime("%S")
        }

        replicated_filename = replicator_config["naming"].format(**substitute_datetimes) + ".iamagesbak"
        replicated_filepath = os.path.join(replicator_config["directory"], replicated_filename)
        shutil.make_archive(replicated_filepath, "zip", tmp)

        if replicator_config["additional_options"]["save_archive_hash"]:
            with open(replicated_filepath + ".zip", "rb") as replicated_file:
                with open(os.path.join(replicator_config["directory"], replicated_filename + ".blake2b.txt"), "w") as replicated_file_hash:
                    replicated_file_hash.write(hashlib.blake2b(replicated_file.read()).hexdigest())

        if len(archives) >= replicator_config["saves"]:
            delete_archive(list(enumerate(archives))[-1][1])
        
        archives[replicated_filename] = {
            "format": replicator_config["format"],
            "created_date": current_datetime.strftime("%Y/%m/%d %H:%M:%S"),
            "has_hash": replicator_config["additional_options"]["save_archive_hash"]
        }

        json.dump(archives, open(archives_filepath, "w"))
elif CMD_PARSED.command == "restore":
    if not CMD_PARSED.archive_name:
        print("Replicated name not provided. Exiting.")
        exit(1)

    print("0/?: Looking for given archive.")
    replicated_info = archives[CMD_PARSED.archive_name]

    if not replicated_info["format"] == SUPPORTED_FORMAT:
        print(f'Replicated archive format is not supported. (expected: {SUPPORTED_FORMAT}, got: {replicated_info["format"]})')
        exit(1)

    replicated_filepath = os.path.join(os.getcwd(), replicator_config["directory"], CMD_PARSED.archive_name + ".zip")

    if replicated_info["has_hash"]:
        print("0/?: Checking archive hash for match.")
        with open(replicated_filepath, "rb") as replicated_archive:
            with open(os.path.join(replicator_config["directory"], CMD_PARSED.archive_name.split(".zip")[0] + ".blake2b.txt"), "r") as replicated_archive_hash:
                if not hashlib.blake2b(replicated_archive.read()).hexdigest() == replicated_archive_hash.read():
                    print("Replicated archive hash doesn't match saved hash in file. Exiting.")
                    exit(1)

    with tempfile.TemporaryDirectory() as tmp:
        print("1/5: Unpacking archive to temporary directory.")
        shutil.unpack_archive(replicated_filepath, tmp)

        print("2/5: Establishing connection to new Iamages database.")
        conn = sqlite3.connect(os.path.join(tmp, "iamages.db"))
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")

        print("3/5: Restoring Files table from CSV.")
        FILES_CSV_PATH = os.path.join(tmp, "Files.csv")
        with open(FILES_CSV_PATH, "r") as csv_files:
            cur.execute("CREATE TABLE Files (FileID INTEGER PRIMARY KEY, FileName TEXT, FileDescription TEXT, FileNSFW INTEGER, FilePrivate INTEGER, FileMime TEXT, FileWidth INTEGER, FileHeight INTEGER, FileHash TEXT, FileLink INTEGER, FileCreatedDate TEXT, FileExcludeSearch INTEGER)")
            pbar = tqdm(csv.DictReader(csv_files))
            for row in pbar:
                cur.execute("INSERT INTO Files (FileID, FileName, FileDescription, FileNSFW, FilePrivate, FileMime, FileWidth, FileHeight, FileHash, FileLink, FileCreatedDate, FileExcludeSearch) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                    row["FileID"], row["FileName"], row["FileDescription"], row["FileNSFW"], row["FilePrivate"], row["FileMime"], row["FileWidth"], row["FileHeight"], row["FileHash"], row["FileLink"], row["FileCreatedDate"], row["FileExcludeSearch"]))
        os.remove(FILES_CSV_PATH)

        print("4/5: Restoring Files_Users table from CSV.")
        FILES_USERS_CSV_PATH = os.path.join(tmp, "Files_Users.csv")
        with open(FILES_USERS_CSV_PATH, "r") as csv_files_users:
            cur.execute("CREATE TABLE Files_Users (FileID INTEGER, UserID INTEGER)")
            pbar = tqdm(csv.DictReader(csv_files_users))
            for row in pbar:
                cur.execute("INSERT INTO Files_Users (FileID, UserID) VALUES (?, ?)", (
                    row["FileID"], row["UserID"]))
        os.remove(FILES_USERS_CSV_PATH)

        print("4/5: Restoring Users table from CSV.")
        USERS_CSV_PATH = os.path.join(tmp, "Users.csv")
        with open(USERS_CSV_PATH, "r") as csv_users:
            cur.execute("CREATE TABLE Users (UserID INTEGER PRIMARY KEY, UserName TEXT, UserPassword TEXT, UserBiography TEXT, UserCreatedDate TEXT)")
            pbar = tqdm(csv.DictReader(csv_users))
            for row in pbar:
                cur.execute("INSERT INTO Users (UserID, UserName, UserPassword, UserBiography, UserCreatedDate) VALUES (?, ?, ?, ?, ?)", (
                    row["UserID"], row["UserName"], row["UserPassword"], row["UserBiography"], row["UserCreatedDate"]))
        os.remove(USERS_CSV_PATH)

        conn.commit()
        conn.close()

        print("5/5: Restoring files storage directory.")
        shutil.rmtree(server_config["files"]["storage"]["directory"])
        shutil.copytree(tmp, server_config["files"]["storage"]["directory"])
elif CMD_PARSED.command == "delete":
    print("1/1: Removing given archive.")
    delete_archive(CMD_PARSED.archive_name)
elif CMD_PARSED.command == "list":
    print("Available replicated archives:\n")
    for save in archives:
        archive_filepath = os.path.join(replicator_config["directory"], save + ".zip")
        if os.path.isfile(archive_filepath):
            print(f'- {save} ({archive_filepath})')
            print(f'    + Created date: {archives[save]["created_date"]}')
            print(f'    + Archive format: {archives[save]["format"]}')
            if archives[save]["has_hash"]:
                archive_hash_filepath = os.path.join(replicator_config["directory"], save + ".blake2b.txt")
                if os.path.isfile(archive_hash_filepath):
                    print(f'    + Archive hash: enabled ({archive_hash_filepath})')
                else:
                    print("     + Archive hash: enabled (not found)")
            else:
                print(f'    + Archive hash: disabled')
        else:
            print(f'- {save} (not found)')
else:
    print(f"Command '{str(CMD_PARSED.command)}' hasn't been implimented yet!")
    
print("")
print("Done!")
