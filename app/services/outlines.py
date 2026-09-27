"""Sermon outlines live in one Drive folder, split into a subfolder per gathering (2pm, 830/1045am)."""

import asyncio
import os
import re
from dataclasses import dataclass

from app.services.drive import FOLDER_MIME, fetch_drive_folder, list_folder_items

OUTLINE_MIMES = ("application/pdf", "wordprocessingml", "msword")
OUTLINE_REGISTRY_KEY = "outline_services"
OUTLINE_SOURCE_PREFIX = "o:"


@dataclass(frozen=True)
class OutlineService:
    slug: str        # "830_1045", "2pm"; "" when the outline sits directly in the root folder
    label: str       # "8.30/10.45am", "2pm"; "" for the root folder
    folder_url: str

    @property
    def pdf_command(self) -> str:
        return f"outline_{self.slug}" if self.slug else "outline"

    @property
    def doc_command(self) -> str:
        return f"outline_doc_{self.slug}" if self.slug else "outline_doc"

    @property
    def title(self) -> str:
        return f"Sermon Outline ({self.label})" if self.label else "Sermon Outline"


def outline_source_id(slug: str) -> str:
    """Ebook source id for a gathering's outline; the root folder keeps the original "outline" id."""
    return f"{OUTLINE_SOURCE_PREFIX}{slug}" if slug else "outline"


def _folder_url(folder_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{folder_id}"


def service_slug(folder_name: str) -> str:
    """"830/1045am" -> "830_1045am" and "2pm" -> "2pm", matching /bulletin_830_1045am and /bulletin_2pm."""
    name = folder_name.lower().replace(".", "")
    slug = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    return slug[:20]


def service_label(folder_name: str) -> str:
    """"830/1045am" -> "8.30/10.45am", the spelling Linktree uses."""
    return re.sub(r"\b(\d{1,2})(\d{2})(?=\D|$)", r"\1.\2", folder_name.strip())


def _start_minutes(folder_name: str) -> int:
    """Rough start time of the first gathering in a folder name, so morning sorts before 2pm."""
    match = re.search(r"(\d+)(?:[.:](\d{2}))?\s*(am|pm)?", folder_name.lower())
    if not match:
        return 24 * 60
    digits, minutes = match.group(1), match.group(2)
    if minutes is None and len(digits) > 2:  # "830" -> 8:30
        digits, minutes = digits[:-2], digits[-2:]
    hour, minute = int(digits), int(minutes or 0)
    if (match.group(3) or "") == "pm" and hour < 12:
        hour += 12
    return hour * 60 + minute


def discover_outline_services(root_url: str | None = None) -> list[OutlineService]:
    """One service per gathering subfolder, plus the root folder if outlines sit there directly."""
    html = fetch_drive_folder(root_url)
    items = list_folder_items(html)
    folders = sorted(
        ((file_id, name) for file_id, name, mime in items if mime == FOLDER_MIME),
        key=lambda folder: _start_minutes(folder[1]),
    )
    services: list[OutlineService] = []
    if any(fragment in mime for _, _, mime in items for fragment in OUTLINE_MIMES):
        services.append(OutlineService("", "", root_url or os.getenv("OUTLINE_FOLDER_URL", "")))

    used: set[str] = set()
    for file_id, name in folders:
        slug = service_slug(name)
        if not slug or slug in used:
            continue
        used.add(slug)
        services.append(OutlineService(slug, service_label(name), _folder_url(file_id)))
    return services


async def discover_outline_services_async(root_url: str | None = None) -> list[OutlineService]:
    return await asyncio.to_thread(discover_outline_services, root_url)
