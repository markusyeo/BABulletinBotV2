import codecs
import json
import logging
import os
import re
from typing import Optional, Tuple

import requests

from app.utils.common import ensure_dir, get_file_checksum

LOGGER = logging.getLogger(__name__)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/91.0.4472.114 Safari/537.36"
)


def _headers():
    return {"User-Agent": USER_AGENT}


def clean_google_drive_link(raw_url: str) -> str:
    """Decode unicode escapes and strip extra quotes from Drive URLs."""
    if not raw_url:
        return ""
    try:
        cleaned = codecs.decode(raw_url, "unicode_escape")
    except Exception:
        cleaned = raw_url
    return cleaned.strip('"').strip("'")


def _extract_viewer_url(drive_url: str) -> Optional[str]:
    response = requests.get(drive_url, headers=_headers(), timeout=60)
    response.raise_for_status()
    match = re.search(
        r"(https://drive\.google\.com/viewerng/upload[^\"]+)", response.text)
    if not match:
        LOGGER.warning("Could not find viewerng URL in Drive HTML")
        return None
    return match.group(1)


def _extract_pdf_link_from_viewer(viewer_url: str) -> Optional[str]:
    response = requests.get(viewer_url, headers=_headers(), timeout=60)
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


def fetch_drive_folder(url: Optional[str] = None) -> str:
    if url is None:
        url = os.getenv("OUTLINE_FOLDER_URL")
        if not url:
            raise ValueError(
                "OUTLINE_FOLDER_URL environment variable is not set")

    response = requests.get(url, headers=_headers(), timeout=60)
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
        if len(item) > 3 and mime_type_fragment in item[3]:
            return item[0]
    return None


def _resolve_drive_filename(response: requests.Response, filename_prefix: str, content: bytes) -> str:
    """Resolve filename from content-disposition or build checksum-based fallback."""
    header = response.headers.get("content-disposition")
    if header:
        match = re.findall(r'filename="?([^"]+)"?', header)
        if match:
            return match[0]

    checksum = get_file_checksum(content)
    return f"{filename_prefix}_{checksum}"


def download_outline(file_id: str, filename_prefix: str = "outline", cache_dir: str = "bulletin_cache") -> Tuple[str, str]:
    ensure_dir(cache_dir)
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    response = requests.get(download_url, allow_redirects=True, timeout=60)
    response.raise_for_status()
    content = response.content

    filename = _resolve_drive_filename(response, filename_prefix, content)

    filepath = os.path.join(cache_dir, filename)
    with open(filepath, "wb") as destination:
        destination.write(content)

    return filepath, filename
