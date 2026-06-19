import hashlib
import os
import re

import requests

CACHE_DIR = "bulletin_cache"


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def get_file_checksum(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


def resolve_filename(response: requests.Response, fallback: str) -> str:
    header = response.headers.get("content-disposition")
    if header:
        match = re.findall(r'filename="?([^"]+)"?', header)
        if match:
            return match[0]
    return fallback
