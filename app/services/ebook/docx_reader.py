"""DOCX to block stream via mammoth, with images captured as EPUB assets.

Runs of empty paragraphs are the writing space sermon outlines leave for notes;
they are kept as blank blocks instead of being collapsed away.
"""

import re
from html import unescape

import mammoth
from bs4 import BeautifulSoup

from app.services.ebook.model import Asset, Block, Book

EMPTY_LINE_EM = 1.4
MAX_NOTE_SPACE_EM = 12.0

STYLE_MAP = "\n".join([
    "p[style-name='Title'] => h1:fresh",
    "p[style-name='Heading 1'] => h1:fresh",
    "p[style-name='Heading 2'] => h2:fresh",
    "p[style-name='Heading 3'] => h3:fresh",
])


def read_docx(path: str, title: str) -> Book:
    book = Book(title=title)
    counter = [0]

    def save_image(image):
        counter[0] += 1
        ext = image.content_type.split("/")[-1].replace("jpeg", "jpg")
        name = f"img{counter[0]:03d}.{ext}"
        with image.open() as fh:
            book.assets.append(Asset(name=name, media_type=image.content_type, data=fh.read()))
        return {"src": f"images/{name}"}

    with open(path, "rb") as fh:
        result = mammoth.convert_to_html(
            fh,
            style_map=STYLE_MAP,
            convert_image=mammoth.images.img_element(save_image),
            ignore_empty_paragraphs=False,
        )

    soup = BeautifulSoup(result.value, "html.parser")
    empty_run = 0
    for element in soup.find_all(recursive=False):
        is_empty = element.name == "p" and not element.get_text(strip=True) and not element.find("img")
        if is_empty:
            empty_run += 1
            continue
        if empty_run:
            book.blocks.append(Block(kind="space", height_em=round(min(MAX_NOTE_SPACE_EM, empty_run * EMPTY_LINE_EM), 1)))
            empty_run = 0
        if element.name in ("h1", "h2", "h3"):
            book.blocks.append(Block(kind=element.name, html=element.decode_contents(), text=element.get_text(" ", strip=True)))
        elif element.name == "img":
            book.blocks.append(_image_block(element, book))
        else:
            html = element.decode() if element.name not in ("p",) else element.decode_contents()
            text = element.get_text(" ", strip=True)
            book.blocks.append(Block(kind="p" if element.name == "p" else "raw", html=html, text=text))
    if empty_run:
        book.blocks.append(Block(kind="space", height_em=round(min(MAX_NOTE_SPACE_EM, empty_run * EMPTY_LINE_EM), 1)))
    return book


def _image_block(img, book: Book) -> Block:
    name = re.sub(r"^images/", "", img.get("src", ""))
    asset = next((a for a in book.assets if a.name == name), None)
    return Block(kind="img", asset=asset, width_pct=100, text=unescape(img.get("alt", "")))
