import logging
import os
import re
from typing import Tuple

import requests
from tenacity import retry, stop_after_attempt, wait_fixed

from app.utils.common import ensure_dir, resolve_filename, CACHE_DIR
from app.utils.http import http_headers

LOGGER = logging.getLogger(__name__)


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


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def download_songbook(url: str, cache_dir: str = CACHE_DIR) -> Tuple[str, str]:
    """Download the songbook PDF and return (filepath, filename)."""
    download_url = _derive_download_url(url)
    LOGGER.info("Downloading songbook from %s", download_url)

    response = requests.get(download_url, headers=http_headers(),
                            allow_redirects=True, timeout=60)
    response.raise_for_status()
    content = response.content

    filename = resolve_filename(response, "songbook.pdf")
    filepath = _persist_file(content, cache_dir, filename)
    return filepath, filename
