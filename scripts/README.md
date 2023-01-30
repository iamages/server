# Iamages v3 to v4 Migration Tool
This tool helps you migrate your Iamages v3 installation to v4.

## Prerequisites
- A current operational installation of Iamages v3.
- All other requirements to run Iamages v4 as detailed in the root README.

## Instructions
1. Create a new storage archive by using `storagearchive.py` in your current installation:

`python3 /path/to/v3/scripts/storagearchive.py archive`

Remember to note down the path of the archive and hash file.

2. Configure the environment variables for v4, namely the database URL.

3. Run `3to4.py` to perform the migration.

`python3 /path/to/v4/scripts/3to4.py /path/to/v3/archive/zip`

4. Confirm the data has been migrated.

5. Optional: remove your v3 installation.