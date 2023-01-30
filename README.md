# Iamages Server

This is the public source code for the Iamages Server. 
An official instance is deployed at https://iamages.jkelol111.me/api, usually using the latest commit available here.

## Server deployment guide

1. Get a copy from releases and extract somewhere/clone this repo to use the bleeding edge version.
2. Install MongoDB.
3. Install dependencies using `poetry` or `pip3` (both `pyproject.toml` and synced `requirements.txt` available, pick your optimal solution)
4. Create the database by using `scripts/mkdb.py`.
5. Start the server using `gunicorn` (a sample startup script is provided as `start_prod_server.sh`).

The following environmental variables may be set to alter the defaults:
- `IAMAGES_MAX_SIZE`: maximum size of one file (in bytes).
- `IAMAGES_DB_HOST`: MongoDB login URL to `iamages` database (requires URL encoding)
- `IAMAGES_JWT_SECRET`: random string used to generate tokens.
- `IAMAGES_SERVER_OWNER`: name of server owner.
- `IAMAGES_SERVER_CONTACT`: contact to the server owner (examples include: mailto, tel link).
- `IAMAGES_SMTP_HOST`: SMTP host address.
- `IAMAGES_SMTP_PORT`: SMTP host port.
- `IAMAGES_SMTP_STARTTLS`: SMTP STARTTLS enabled (recommended).
- `IAMAGES_SMTP_USERNAME`: SMTP username (optional).
- `IAMAGES_SMTP_PASSWORD`: SMTP password (optional).
- `IAMAGES_SMTP_FROM`: email address used in `From` fields.

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
