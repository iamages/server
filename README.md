# Iamages Server

This is the public source code for the Iamages Server. 
An official instance is deployed at https://iamages.uber.space/iamages/api/v3, usually using the latest commit available here.

## Server deployment guide

1. Get a copy from releases and extract somewhere/clone this repo to use the bleeding edge version.
2. Install RethinkDB using your preferred method (you can build it yourself using our Multipass build scripts as well: https://github.com/iamages/rethinkdb-multipass-build).
3. Install dependencies using `pipenv` or `pip3` (both `Pipfile` and synced `requirements.txt` available, pick your optimal solution)
4. Create the database by using `scripts/mkdb.py`.
5. Start the server using `gunicorn` (a sample startup script is provided as `start_prod_server.sh`).

The following environmental variables may be set to alter the defaults:
- `IAMAGES_MAX_SIZE`: maximum size of one file (in bytes).
- `IAMAGES_ACCEPT_MIMES`: accept mime types for files (in JSON array format).
- `IAMAGES_STORAGE_DIR`: path to your storage directory.
- `IAMAGES_DB_HOST`: address to your RethinkDB instance.
- `IAMAGES_DB_PORT`: port of your RethinkDB instance.
- `IAMAGES_DB_USER`: username with permissions to access the Iamages database.
- `IAMAGES_DB_PWD`: password to above user.
- `IAMAGES_SERVER_OWNER`: name of server owner (optional).
- `IAMAGES_SERVER_CONTACT`: contact to the server owner (optional, examples include: mailto, tel link).

Periodically check back here for new releases/commits, and update the server using step 1 and 2 (3 might be required too, along with 'Using database/storage layout upgrader' below)

## Server development guide

Follow [Server deployment guide](#server-deployment-guide) above until step 4.

5. Install Traefik.
6. Start Treafik proxy (a sample startup script is provided as `start_dev_proxy.sh`).
7. Start the server using `uvicorn` (a sample startup script is provided as `start_dev_server.sh`).

Changes in the code will automatically be reloaded if you start the server using this method.

## Using database/storage layout upgrader

Most of the time, Iamages Server updates are as simple as getting a new copy, replacing the older one, and restart the server. However, database/storage layout changes may occur between updates (rarely), in which case you will have to follow this section in addition to updating the server.

1. Archive/backup the current server using `scripts/storagearchive.py` (view instructions in `scripts/README.md`).
2. Run `scripts/dbupgrade.py`
3. Start the new server. If no errors come up, you should be good to go (test some endpoints for good measure).

If errors come up, it's a matter of rolling back to the older server version, and restoring an archive/backup using `scripts/storagearchive.py`.

## Additional reading

- README files for the various scripts can be viewed in `scripts/README.md`.
