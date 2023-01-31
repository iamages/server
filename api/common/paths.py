from pathlib import Path

from .settings import server_config

if not server_config.iamages_storage_dir.exists():
    server_config.iamages_storage_dir.mkdir()

FILES_PATH = Path(server_config.iamages_storage_dir, "files")
if not FILES_PATH.exists():
    FILES_PATH.mkdir()

THUMBS_PATH = Path(server_config.iamages_storage_dir, "thumbs")
if not THUMBS_PATH.exists():
    THUMBS_PATH.mkdir()
