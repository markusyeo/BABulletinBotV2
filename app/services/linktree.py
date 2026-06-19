import logging
import os
import re
import asyncio
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

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


@dataclass(frozen=True)
class DriveLink:
    command: str
    label: str
    url: str


def _slugify_command(label: str) -> str:
    normalized = label.lower()
    normalized = normalized.replace("8.30/10.45am", "830_1045")
    normalized = normalized.replace("10.45", "1045").replace("8.30", "830")
    if "bulletin" in normalized:
        normalized = normalized.replace("gathering", "")
        normalized = normalized.replace("sunday", "")
        normalized = re.sub(r"\bbulletin\b", "", normalized)
        prefix = "bulletin"
    else:
        prefix = ""
    suffix = re.sub(r"[^a-z0-9]+", "_", normalized)
    suffix = re.sub(r"_+", "_", suffix).strip("_")
    if prefix and suffix:
        slug = f"{prefix}_{suffix}"
    else:
        slug = suffix or prefix or "link"
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:32]


def _is_google_drive_url(url: str) -> bool:
    return urlparse(url).netloc.lower().endswith("drive.google.com")


def _has_drive_file_id(url: str) -> bool:
    return bool(
        re.search(r"/file/d/[a-zA-Z0-9_-]+", url)
        or re.search(r"[?&]id=[a-zA-Z0-9_-]+", url)
    )


def resolve_final_url(url: str) -> str:
    """Resolve short URLs and Linktree redirects to their final destination."""
    if not url:
        return ""
    try:
        with requests.get(
            url,
            headers=_get_headers(),
            allow_redirects=True,
            timeout=30,
            stream=True,
        ) as response:
            response.raise_for_status()
            return response.url
    except Exception as exc:
        LOGGER.warning("Could not resolve URL '%s': %s", url, exc)
        return url


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


def find_drive_links(html_content: str) -> list[DriveLink]:
    """Resolve every Linktree anchor and return Google Drive-backed links."""
    entries = _extract_linktree_entries(html_content)
    resolved_entries = [
        (label, resolve_final_url(href))
        for label, href in entries
    ]
    return _build_drive_links(resolved_entries)


async def find_drive_links_async(
    html_content: str,
    max_concurrency: int = 10,
) -> list[DriveLink]:
    """Resolve Linktree anchors concurrently and return Google Drive-backed links."""
    entries = _extract_linktree_entries(html_content)
    semaphore = asyncio.Semaphore(max_concurrency)

    async def resolve_entry(label: str, href: str) -> tuple[str, str]:
        async with semaphore:
            return label, await asyncio.to_thread(resolve_final_url, href)

    resolved_entries = await asyncio.gather(
        *(resolve_entry(label, href) for label, href in entries)
    )
    return _build_drive_links(list(resolved_entries))


def _extract_linktree_entries(html_content: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html_content, "html.parser")
    entries: list[tuple[str, str]] = []

    for a_tag in soup.find_all("a"):
        label = " ".join(a_tag.get_text(" ", strip=True).split())
        href = a_tag.get("href")
        if not label or not href:
            continue
        entries.append((label, href))

    return entries


def _build_drive_links(resolved_entries: list[tuple[str, str]]) -> list[DriveLink]:
    drive_links: list[DriveLink] = []
    used_commands: set[str] = set()

    for label, resolved_url in resolved_entries:
        if (
            not _is_google_drive_url(resolved_url)
            or not _has_drive_file_id(resolved_url)
        ):
            LOGGER.info(
                "Skipping Linktree entry without Google Drive file target: %s -> %s",
                label,
                resolved_url,
            )
            continue

        command = _slugify_command(label)
        base_command = command
        suffix = 2
        while command in used_commands:
            command = f"{base_command[:29]}_{suffix}"
            suffix += 1
        used_commands.add(command)

        drive_links.append(
            DriveLink(command=command, label=label, url=resolved_url)
        )

    return drive_links


def find_bulletin_links(html_content: str) -> list[DriveLink]:
    """Find all Google Drive-backed bulletin links exposed on Linktree."""
    return [
        link for link in find_drive_links(html_content)
        if "bulletin" in link.label.lower()
    ]


def _find_link_by_text(html_content: str, keyword: str) -> Optional[str]:
    soup = BeautifulSoup(html_content, "html.parser")
    for a_tag in soup.find_all("a"):
        text = a_tag.get_text()
        if keyword in text:
            return a_tag.get("href")
    LOGGER.warning("No link found for keyword '%s'", keyword)
    return None


def find_bulletin_morning_link(html_content: str) -> Optional[str]:
    """Locate the 8.30/10.45am Gathering Bulletin link inside the Linktree HTML."""
    return _find_link_by_text(html_content, "8.30/10.45am Gathering Bulletin")


def find_bulletin_2pm_link(html_content: str) -> Optional[str]:
    """Locate the 2pm Gathering Bulletin link inside the Linktree HTML."""
    return _find_link_by_text(html_content, "2pm Gathering Bulletin")


def find_songbook_link(html_content: str) -> Optional[str]:
    """Locate the Songbook link inside the Linktree HTML."""
    return _find_link_by_text(html_content, "Songbook")
