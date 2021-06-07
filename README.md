# Iamages Server

This is the public source code for the Iamages Server. 
An official instance is deployed at https://iamages.uber.space/iamages/api/v2, usually using the latest commit available here.

## Server deployment guide

1. Get a copy from releases and extract somewhere/clone this repo to use the bleeding edge version.
2. Install RethinkDB using your preferred method (you can build it yourself using our Multipass build scripts as well: https://github.com/iamages/rethinkdb-multipass-build).
3. Install dependencies using `pipenv` or `pip3` (both `Pipfile` and synced `requirements.txt` available, pick your optimal solution)
5. Create the database by using `iamages_mkdb.py`.
6. Start the server using `gunicorn` (a sample startup script is provided as `start_prod_server.sh`).

Periodically check back here for new releases/commits, and update the server using step 1 and 2 (3 might be required too, along with [Using database/storage layout upgrader]() below)

## Using database/storage layout upgrader
**IMPORTANT: Upgrading to database layout v3 (now using RethinkDB) will require much more work. If you're currently running v2,  please follow in README_UPGRADE.md.**

Most of the time, Iamages Server updates are as simple as getting a new copy, replacing the older one, and restart the server. However, database/storage layout changes may occur between updates (rarely), in which case you will have to follow this section in addition to updating the server.

1. Archive/backup the current server using `iamages_replicator.py` (follow [Using replicator](#using-replicator) below to configure the script).
2. Run `iamages_updb.py`
3. Start the new server. If no errors come up, you should be good to go (test some endpoints for good measure).

If errors come up, it's a matter of rolling back to the older server version, and restoring an archive/backup using `iamages_replicator.py`.
