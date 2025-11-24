import logging
import os
from typing import Optional

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_fixed

LOGGER = logging.getLogger(__name__)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/91.0.4472.114 Safari/537.36"
)


def _get_headers():
    return {"User-Agent": USER_AGENT}


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def fetch_linktree(url: Optional[str] = None) -> str:
    """Fetch and return the Linktree HTML."""
    if url is None:
        url = os.getenv("LINKTREE_URL")
        if not url:
            raise ValueError("LINKTREE_URL environment variable is not set")

    response = requests.get(url, headers=_get_headers(), timeout=30)
    response.raise_for_status()
    return response.text


def _find_link_by_text(html_content: str, keyword: str) -> Optional[str]:
    soup = BeautifulSoup(html_content, "html.parser")
    for a_tag in soup.find_all("a"):
        text = a_tag.get_text()
        if keyword in text:
            return a_tag.get("href")
    LOGGER.warning("No link found for keyword '%s'", keyword)
    return None


def find_bulletin_link(html_content: str) -> Optional[str]:
    """Locate the Sunday Bulletin link inside the Linktree HTML."""
    return _find_link_by_text(html_content, "Sunday Bulletin")


def find_songbook_link(html_content: str) -> Optional[str]:
    """Locate the Songbook link inside the Linktree HTML."""
    return _find_link_by_text(html_content, "Songbook")
