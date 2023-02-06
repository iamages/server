from pathlib import Path

from .settings import api_settings

IMAGES_PATH = Path(api_settings.storage_dir, "images")
if not IMAGES_PATH.exists():
    IMAGES_PATH.mkdir()

THUMBNAILS_PATH = Path(api_settings.storage_dir, "thumbnails")
if not THUMBNAILS_PATH.exists():
    THUMBNAILS_PATH.mkdir()
