"""Convert a downloaded PDF or DOCX into a device-sized EPUB or KEPUB, with a disk cache."""

import hashlib
import logging
import os
import re
from dataclasses import dataclass

from app.services.ebook.devices import DeviceProfile
from app.services.ebook.docx_reader import read_docx
from app.services.ebook.epub_writer import write_epub
from app.services.ebook.pdf_reader import read_pdf
from app.utils.common import CACHE_DIR, ensure_dir

LOGGER = logging.getLogger(__name__)

EBOOK_CACHE_DIR = os.path.join(CACHE_DIR, "ebooks")
FORMATS = {"epub": ".epub", "kepub": ".kepub.epub"}
SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


class UnsupportedSource(Exception):
    pass


@dataclass(frozen=True)
class ConvertedBook:
    path: str
    filename: str
    cache_key: str


def convert_to_ebook(
    source_path: str,
    device: DeviceProfile,
    fmt: str,
    author: str,
    cache_dir: str = EBOOK_CACHE_DIR,
) -> ConvertedBook:
    if fmt not in FORMATS:
        raise ValueError(f"Unknown ebook format: {fmt}")
    ext = os.path.splitext(source_path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedSource(f"{ext or 'this file type'} cannot be converted; only PDF and DOCX are supported.")

    with open(source_path, "rb") as fh:
        digest = hashlib.sha1(fh.read()).hexdigest()[:12]
    stem = os.path.splitext(os.path.basename(source_path))[0]
    cache_key = f"{digest}-{device.key}-{fmt}"
    filename = _safe(f"{stem} ({device.name})") + FORMATS[fmt]
    ensure_dir(cache_dir)
    output = os.path.join(cache_dir, f"{cache_key}{FORMATS[fmt]}")

    if os.path.exists(output):
        LOGGER.info("Ebook cache hit: %s", output)
        return ConvertedBook(path=output, filename=filename, cache_key=cache_key)

    LOGGER.info("Converting %s -> %s for %s", source_path, fmt, device.name)
    book = read_pdf(source_path, device, stem) if ext == ".pdf" else read_docx(source_path, stem)
    tmp = output + ".part"
    write_epub(book, tmp, kepub=(fmt == "kepub"), author=author)
    os.replace(tmp, output)
    return ConvertedBook(path=output, filename=filename, cache_key=cache_key)


def _safe(name: str) -> str:
    """Strip characters that file systems or Telegram clients reject in file names."""
    return re.sub(r"[\\/:*?\"<>|]+", "-", name).strip(" -") or "document"
