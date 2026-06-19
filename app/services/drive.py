import codecs
import json
import logging
import os
import re
from typing import Optional, Tuple

import requests
from tenacity import retry, stop_after_attempt, wait_fixed

from app.utils.common import ensure_dir, get_file_checksum, resolve_filename, CACHE_DIR
from app.utils.http import http_headers

LOGGER = logging.getLogger(__name__)


def clean_google_drive_link(raw_url: str) -> str:
    """Decode unicode escapes and strip extra quotes from Drive URLs."""
    if not raw_url:
        return ""
    try:
        cleaned = codecs.decode(raw_url, "unicode_escape")
    except Exception:
        cleaned = raw_url
    return cleaned.strip('"').strip("'")


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def _extract_viewer_url(drive_url: str) -> Optional[str]:
    response = requests.get(drive_url, headers=http_headers(), timeout=60)
    response.raise_for_status()
    match = re.search(
        r"(https://drive\.google\.com/viewer/upload[^\"]+)", response.text)
    if not match:
        LOGGER.warning("Could not find viewer URL in Drive HTML")
        return None
    return match.group(1)


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def _extract_pdf_link_from_viewer(viewer_url: str) -> Optional[str]:
    response = requests.get(viewer_url, headers=http_headers(), timeout=60)
    response.raise_for_status()
    content = response.text
    if content.startswith(")]}'"):
        content = content[4:].strip()
    return content


def extract_pdf_link_from_google(drive_url: str) -> Optional[str]:
    try:
        viewer_url = _extract_viewer_url(drive_url)
        if not viewer_url:
            return None
        cleaned_url = clean_google_drive_link(viewer_url)
        content = _extract_pdf_link_from_viewer(cleaned_url)
        if not content:
            return None

        data = json.loads(content)
        return data.get("pdf")
    except Exception as exc:
        LOGGER.error("Error extracting direct PDF link: %s", exc)
        return None


def extract_drive_file_id(drive_url: str) -> Optional[str]:
    """Extract a Google Drive file id from common file URL formats."""
    patterns = [
        r"/file/d/([a-zA-Z0-9_-]+)",
        r"[?&]id=([a-zA-Z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, drive_url)
        if match:
            return match.group(1)
    return None


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def fetch_drive_folder(url: Optional[str] = None) -> str:
    if url is None:
        url = os.getenv("OUTLINE_FOLDER_URL")
        if not url:
            raise ValueError(
                "OUTLINE_FOLDER_URL environment variable is not set")

    response = requests.get(url, headers=http_headers(), timeout=60)
    response.raise_for_status()
    return response.text


def extract_outline_file_id(html_content: str, mime_type_fragment: str) -> Optional[str]:
    """Parse the Drive folder HTML and return the first file id matching a mime fragment."""
    match = re.search(r"window\['_DRIVE_ivd'\] = '([^']+)'", html_content)
    if not match:
        LOGGER.error("Could not find _DRIVE_ivd in HTML")
        return None

    encoded_json = match.group(1)
    try:
        decoded_json = encoded_json.encode("utf-8").decode("unicode_escape")
        data = json.loads(decoded_json)
    except Exception as exc:
        LOGGER.error("Error decoding Drive JSON: %s", exc)
        return None

    if not data or not isinstance(data, list) or not data[0]:
        return None

    for item in data[0]:
        # item[0] = file id, item[3] = mime type
        if len(item) > 3 and mime_type_fragment in item[3]:
            return item[0]
    return None


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def download_outline(file_id: str, filename_prefix: str = "outline", cache_dir: str = CACHE_DIR) -> Tuple[str, str]:
    ensure_dir(cache_dir)
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    response = requests.get(download_url, headers=http_headers(), allow_redirects=True, timeout=60)
    response.raise_for_status()
    content = response.content

    checksum_fallback = f"{filename_prefix}_{get_file_checksum(content)}"
    filename = resolve_filename(response, checksum_fallback)

    filepath = os.path.join(cache_dir, filename)
    with open(filepath, "wb") as destination:
        destination.write(content)

    return filepath, filename
