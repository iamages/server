# Upgrade Guide

This guide is aimed towards server operators running server storage format `2` (check your `servercfg.json` file). If you're running something older, migration can be done by using an older `iamages_updb.py` first, then come back to this guide (you may find these in one of the older releases).

## Main changes with storage format 3
- Use UUIDs to prevent scraping data.
- Move to NoSQL DB RethinkDB for future growth and enhancements.
- Deprecate hash matching deduplication to prevent tracing files.

## Presequisites
- RethinkDB installed.
- Python 3.8 and above.

## Instructions
1. Inform users about downtime and shut down your server.
2. **VERY IMPORTANT:** Make a manual copy of your existing storage folder (containing `iamages.db`) **Newer `storagearchive.py` will not work with this old database format!**
3. Copy your `servercfg.json` to `scripts`.
4. Run `scripts/dbupgrade.py` and wait patiently. (migration will take time with large file collections).
    - If you have not configured RethinkDB's admin account with your own password, press Enter/Return at the password prompt (empty string).
    - You may want to make sure you have more space than necessary, as the migration will duplicate files due to the removal of file hashes. A good rule of thumb would be x2 the current used space.
    - Broken files in the database will not be migrated over. Take note of those and restore them manually through the command line server management tool.
4. Check your current server script directory.
    - `servercfg.json` should still be there, but:
        - It's no longer used. Refer to `README.md` for more information.
        - You may remove it if you wish.
        - You may change your RethinkDB credentials yourself or stick with the defaults (use `scripts/dbctl.py` to automate these tasks.)
        - You may change your RethinkDB port and host address as well. (remember to modify your startup script!)
5. Check your files storage directory.
    - You may delete `iamages.db` after confirming the database has been successful migrated to RethinkDB.
6. Run the server using your startup script (a sample one is provided in your server script directory as `start_prod_server.sh`)
7. If all goes well, you should be able to access the new API at `/iamages/api/v2` (note the v2, this is the new API that has breaking changes.)

## Caveats
- You will no longer be able to run Iamages without any external database software installed besides what Python supports by default.
- API v1 is now deprecated.
