"""Files the bot can hand to the ebook converter, and how to get them onto disk."""

import asyncio
from dataclasses import dataclass

from app.services.downloads import download_songbook
from app.services.drive import (
    download_outline,
    extract_drive_file_id,
    extract_outline_file_id,
    fetch_drive_folder,
)
from app.services.linktree import DriveLink, fetch_linktree, find_songbook_link

DRIVE_LINK_REGISTRY_KEY = "drive_links"
DRIVE_PREFIX = "d:"


class SourceUnavailable(Exception):
    pass


@dataclass(frozen=True)
class EbookSource:
    id: str
    label: str


STATIC_SOURCES = [
    EbookSource("songbook", "Songbook"),
    EbookSource("outline_pdf", "Sermon Outline (PDF)"),
    EbookSource("outline_doc", "Sermon Outline (DOCX)"),
]


def drive_source_id(command: str) -> str:
    return f"{DRIVE_PREFIX}{command}"


def list_sources(application) -> list[EbookSource]:
    registry: dict[str, DriveLink] = application.bot_data.get(DRIVE_LINK_REGISTRY_KEY, {})
    dynamic = [EbookSource(drive_source_id(command), link.label) for command, link in registry.items()]
    return dynamic + STATIC_SOURCES


def source_label(application, source_id: str) -> str:
    for source in list_sources(application):
        if source.id == source_id:
            return source.label
    return source_id


async def fetch_source_file(application, source_id: str) -> str:
    """Download the source document into the cache directory and return its path."""
    if source_id.startswith(DRIVE_PREFIX):
        command = source_id[len(DRIVE_PREFIX):]
        link: DriveLink | None = application.bot_data.get(DRIVE_LINK_REGISTRY_KEY, {}).get(command)
        file_id = extract_drive_file_id(link.url) if link else None
        if not file_id:
            raise SourceUnavailable("That file is no longer listed. Use /refresh and try again.")
        path, _ = await asyncio.to_thread(download_outline, file_id, filename_prefix=command)
        return path

    if source_id == "songbook":
        html = await asyncio.to_thread(fetch_linktree)
        url = find_songbook_link(html)
        if not url:
            raise SourceUnavailable("The songbook link is missing from Linktree.")
        path, _ = await asyncio.to_thread(download_songbook, url)
        return path

    if source_id in ("outline_pdf", "outline_doc"):
        html = await asyncio.to_thread(fetch_drive_folder)
        if source_id == "outline_pdf":
            file_id = extract_outline_file_id(html, "application/pdf")
        else:
            file_id = extract_outline_file_id(html, "wordprocessingml") or extract_outline_file_id(html, "msword")
        if not file_id:
            raise SourceUnavailable("No sermon outline was found in the Drive folder.")
        path, _ = await asyncio.to_thread(download_outline, file_id, filename_prefix=source_id)
        return path

    raise SourceUnavailable("Unknown file.")
