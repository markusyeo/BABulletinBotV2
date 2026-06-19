import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from app.services.cache import CacheStore
from app.services.downloads import download_songbook
from app.services.drive import (
    download_outline,
    extract_drive_file_id,
    extract_outline_file_id,
    extract_pdf_link_from_google,
    fetch_drive_folder,
)
from app.services.linktree import DriveLink, fetch_linktree, find_songbook_link

LOGGER = logging.getLogger(__name__)


@dataclass
class Document:
    telegram_ref: Optional[str] = None   # file_id or direct URL — send directly
    filepath: Optional[str] = None        # downloaded file path — send as upload
    filename: Optional[str] = None
    drive_file_id: Optional[str] = None   # for post-upload caching
    source_url: Optional[str] = None      # original URL for post-upload caching

    @property
    def found(self) -> bool:
        return bool(self.telegram_ref or self.filepath)


async def resolve_drive_document(drive_link: DriveLink, cache: CacheStore) -> Document:
    file_id = extract_drive_file_id(drive_link.url)

    if file_id:
        cached = cache.get_file_id_for_drive_id(file_id)
        if cached:
            return Document(telegram_ref=cached, drive_file_id=file_id)

    direct_link = cache.get_direct_link(drive_link.url)
    if not direct_link:
        direct_link = await asyncio.to_thread(extract_pdf_link_from_google, drive_link.url)
        if direct_link:
            cache.set_direct_link(drive_link.url, direct_link)

    if direct_link:
        return Document(telegram_ref=direct_link)

    if not file_id:
        return Document()

    filepath, filename = await asyncio.to_thread(
        download_outline, file_id, filename_prefix=drive_link.command
    )
    return Document(filepath=filepath, filename=filename, drive_file_id=file_id)


async def resolve_outline_pdf(cache: CacheStore) -> Document:
    html = await asyncio.to_thread(fetch_drive_folder)
    file_id = extract_outline_file_id(html, "application/pdf")
    if not file_id:
        return Document()

    view_url = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
    direct_link = cache.get_direct_link(view_url)
    if not direct_link:
        direct_link = await asyncio.to_thread(extract_pdf_link_from_google, view_url)
        if direct_link:
            cache.set_direct_link(view_url, direct_link)

    if not direct_link:
        return Document()
    return Document(telegram_ref=direct_link, source_url=view_url)


async def resolve_outline_doc(cache: CacheStore) -> Document:
    html = await asyncio.to_thread(fetch_drive_folder)
    file_id = extract_outline_file_id(html, "wordprocessingml")
    if not file_id:
        file_id = extract_outline_file_id(html, "msword")
    if not file_id:
        return Document()

    cached = cache.get_file_id_for_drive_id(file_id)
    if cached:
        return Document(telegram_ref=cached, drive_file_id=file_id)

    filepath, filename = await asyncio.to_thread(
        download_outline, file_id, filename_prefix="outline_doc"
    )
    return Document(filepath=filepath, filename=filename, drive_file_id=file_id)


async def resolve_songbook(cache: CacheStore) -> Document:
    html = await asyncio.to_thread(fetch_linktree)
    link = find_songbook_link(html)
    if not link:
        return Document()

    cached = cache.get_file_id_for_url(link)
    if cached:
        return Document(telegram_ref=cached, source_url=link)

    filepath, filename = await asyncio.to_thread(download_songbook, link)
    return Document(filepath=filepath, filename=filename, source_url=link)
