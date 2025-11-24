import logging
import os
import re
from typing import Tuple

import requests

from app.utils.common import ensure_dir

LOGGER = logging.getLogger(__name__)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/91.0.4472.114 Safari/537.36"
)


def _headers():
    return {"User-Agent": USER_AGENT}


def _derive_download_url(view_url: str) -> str:
    match = re.search(r"/file/d/([a-zA-Z0-9_-]+)", view_url)
    if not match:
        return view_url
    file_id = match.group(1)
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def _persist_file(content: bytes, cache_dir: str, filename: str) -> str:
    ensure_dir(cache_dir)
    filepath = os.path.join(cache_dir, filename)
    if os.path.exists(filepath):
        LOGGER.info("File already cached: %s", filepath)
        return filepath

    with open(filepath, "wb") as destination:
        destination.write(content)
    LOGGER.info("Cached file at %s", filepath)
    return filepath


def _resolve_filename(response: requests.Response, fallback: str) -> str:
    header = response.headers.get("content-disposition")
    if header:
        match = re.findall(r'filename="?([^"]+)"?', header)
        if match:
            return match[0]
    return fallback


def download_songbook(url: str, cache_dir: str = "bulletin_cache") -> Tuple[str, str]:
    """Download the songbook PDF and return (filepath, filename)."""
    download_url = _derive_download_url(url)
    LOGGER.info("Downloading songbook from %s", download_url)

    response = requests.get(download_url, headers=_headers(),
                            allow_redirects=True, timeout=60)
    response.raise_for_status()
    content = response.content

    fallback_name = f"songbook.pdf"
    filename = _resolve_filename(response, fallback_name)
    filepath = _persist_file(content, cache_dir, filename)
    return filepath, filename
