# Scripts reference

This README details the various functionality of the scripts found in this directory.

## Common information

When running these scripts, as well as the server, several environment variables need to be provided:
- `STORAGE_DIR`: path to your Iamages storage (required by `dbctl.py`).
- `ARCHIVE_DIR`: path to your storage archive directory (only required by `storagearchive.py`).

## dbctl.py

Manages the Iamages database.

Usage: `dbctl.py command [data]`

- `command`:
    - `chpwd`: Change the password for the `iamages` database account.
    - `getfile`: Get a file given an UUID.
    - `getuser`: Get an user given an username.
- `[data]`: data provided to `command`. (optional)

## dbupgrade.py

Upgrades the Iamages storage (including database).

Usage: `dbupgrade.py`

## mkdb.py

Makes the Iamages database.

Usage: `mkdb.py`

## storagearchive.py

Manages Iamages storage archives.

Usage: `storagearchive.py command [data]`

- `command`:
    - `list`: Lists existing archives.
    - `archive`: Creates a new archive.
    - `restore`: Restores an existing archive.
- `[data]` data provided to `command`. (optional)
