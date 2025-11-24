import hashlib
import os
from datetime import datetime, timedelta


def ensure_dir(path: str) -> None:
    """Create the directory if it does not already exist."""
    os.makedirs(path, exist_ok=True)


def get_file_checksum(content: bytes) -> str:
    """Return the MD5 checksum for the provided content."""
    return hashlib.md5(content).hexdigest()
