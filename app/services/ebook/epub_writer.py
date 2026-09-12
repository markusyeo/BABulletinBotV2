"""Write a Book as a reflowable EPUB 3, optionally in Kobo's KEPUB dialect.

Package layout and the reflowable stylesheet are adapted from KoboForge's
epub-package.js (Alphaeus Ng, MIT). KEPUB support wraps each sentence in the
``koboSpan`` elements Kobo's native reader uses for pagination and highlights,
which is what the kepubify tool does.
"""

import re
import uuid
import zipfile
from datetime import datetime, timezone
from html import escape

from bs4 import BeautifulSoup, NavigableString

from app.services.ebook.model import Block, Book

STYLESHEET = """
html,body{height:auto !important;max-height:none !important;overflow:visible !important;}
body{font-family:Georgia,"Times New Roman",serif;line-height:1.5;margin:3% 4%;color:#111;orphans:2;widows:2;}
h1,h2,h3{line-height:1.25;page-break-after:avoid;}
h1{font-size:1.4em;margin:1.2em 0 .6em;text-transform:uppercase;letter-spacing:.04em;}
h2{font-size:1.2em;margin:1.1em 0 .4em;}
h3{font-size:1em;margin:1.1em 0 .25em;font-weight:700;color:#333;}
p{margin:0 0 .7em;text-align:left;}
h3 + p{margin-top:0;}
sup{font-size:.72em;line-height:1;vertical-align:super;}
a{color:inherit;text-decoration:underline;}
figure{margin:.8em auto;text-align:center;page-break-inside:avoid;}
figure img{display:inline-block;max-width:100%;height:auto;}
ul,ol{margin:0 0 .7em 1.25em;padding-left:.5em;}
li{margin:.25em 0;}
table{width:100%;border-collapse:collapse;margin:1em 0;font-size:.9em;}
th,td{border:1px solid #555;padding:4px 6px;text-align:left;vertical-align:top;}
""".strip()

SENTENCE_RE = re.compile(r"[^.!?]+[.!?]*\s*")


def write_epub(book: Book, output_path: str, kepub: bool, author: str) -> None:
    chapters = _chapters(book)
    identifier = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, output_path)}"
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with zipfile.ZipFile(output_path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/styles.css", STYLESHEET, compress_type=zipfile.ZIP_DEFLATED)
        for asset in book.assets:
            zf.writestr(f"OEBPS/images/{asset.name}", asset.data, compress_type=zipfile.ZIP_DEFLATED)
        for index, (title, blocks) in enumerate(chapters, start=1):
            body = "".join(_block_xhtml(b) for b in blocks)
            if kepub:
                body = _kepubify(body)
            zf.writestr(f"OEBPS/chapter-{index}.xhtml", _chapter_xhtml(title, body, book.language), compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/nav.xhtml", _nav_xhtml(chapters, book.language), compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/toc.ncx", _ncx(book.title, identifier, chapters), compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf", _opf(book, chapters, identifier, modified, author), compress_type=zipfile.ZIP_DEFLATED)


# --- structure ---------------------------------------------------------------

MANY_SUBHEADINGS = 4
FEW_SECTIONS = 2


def _chapters(book: Book) -> list[tuple[str, list[Block]]]:
    h1_count = sum(b.kind == "h1" for b in book.blocks)
    h2_count = sum(b.kind == "h2" for b in book.blocks)
    # A songbook has one or two section titles and hundreds of song titles: split on the songs.
    split_kind = "h2" if (h1_count <= FEW_SECTIONS and h2_count >= MANY_SUBHEADINGS) or not h1_count else "h1"
    chapters: list[tuple[str, list[Block]]] = []
    current_title = book.title
    current: list[Block] = []
    for block in book.blocks:
        if block.kind == split_kind and current:
            chapters.append((current_title, current))
            current = []
        if block.kind == split_kind:
            current_title = block.text or current_title
        current.append(block)
    if current or not chapters:
        chapters.append((current_title, current or [Block(kind="p", html="(Empty document)", text="")]))
    return chapters


def _block_xhtml(block: Block) -> str:
    if block.kind == "img":
        if block.asset is None:
            return ""
        alt = escape(block.text or "image", quote=True)
        return (f'<figure><img src="images/{block.asset.name}" alt="{alt}" '
                f'style="width:{block.width_pct}%"/></figure>')
    if block.kind == "raw":
        return _xhtml(block.html)
    if block.kind in ("h1", "h2", "h3"):
        return f"<{block.kind}>{_heading_inner(block.html)}</{block.kind}>"
    return f"<{block.kind}>{_xhtml(block.html)}</{block.kind}>"


def _heading_inner(html: str) -> str:
    """Headings get their own typography; drop inline bold/italic but keep links and breaks."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["strong", "em", "b", "i", "span"]):
        tag.unwrap()
    return soup.decode(formatter="minimal")


def _xhtml(fragment: str) -> str:
    """Re-serialise an HTML fragment so void elements are self-closed for XHTML."""
    return BeautifulSoup(fragment, "html.parser").decode(formatter="minimal")


def _kepubify(body_html: str) -> str:
    soup = BeautifulSoup(body_html, "html.parser")
    paragraph = 0
    for element in soup.find_all(["h1", "h2", "h3", "p", "li", "td", "th", "figure"]):
        paragraph += 1
        segment = 0
        for node in list(element.descendants):
            if not isinstance(node, NavigableString) or not node.strip():
                continue
            if node.find_parent(class_="koboSpan") is not None:
                continue
            for sentence in SENTENCE_RE.findall(str(node)):
                segment += 1
                span = soup.new_tag("span", attrs={"class": "koboSpan", "id": f"kobo.{paragraph}.{segment}"})
                span.string = sentence
                node.insert_before(span)
            node.extract()
    inner = soup.decode(formatter="minimal")
    return f'<div id="book-columns"><div id="book-inner">{inner}</div></div>'


# --- package files -----------------------------------------------------------

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""


def _chapter_xhtml(title: str, body: str, lang: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{escape(lang)}" lang="{escape(lang)}">
<head>
  <title>{escape(title)}</title>
  <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>
{body}
</body>
</html>"""


def _nav_xhtml(chapters, lang: str) -> str:
    items = "\n".join(
        f'      <li><a href="chapter-{i}.xhtml">{escape(title)}</a></li>'
        for i, (title, _) in enumerate(chapters, start=1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{escape(lang)}">
<head><title>Contents</title><link rel="stylesheet" type="text/css" href="styles.css"/></head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>Contents</h1>
    <ol>
{items}
    </ol>
  </nav>
</body>
</html>"""


def _ncx(title: str, identifier: str, chapters) -> str:
    points = "\n".join(
        f"""    <navPoint id="navPoint-{i}" playOrder="{i}">
      <navLabel><text>{escape(chapter_title)}</text></navLabel>
      <content src="chapter-{i}.xhtml"/>
    </navPoint>"""
        for i, (chapter_title, _) in enumerate(chapters, start=1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{escape(identifier)}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{escape(title)}</text></docTitle>
  <navMap>
{points}
  </navMap>
</ncx>"""


def _opf(book: Book, chapters, identifier: str, modified: str, author: str) -> str:
    chapter_items = "\n".join(
        f'    <item id="ch{i}" href="chapter-{i}.xhtml" media-type="application/xhtml+xml"/>'
        for i in range(1, len(chapters) + 1)
    )
    image_items = "\n".join(
        f'    <item id="img{i}" href="images/{escape(a.name)}" media-type="{escape(a.media_type)}"/>'
        for i, a in enumerate(book.assets, start=1)
    )
    spine = "\n".join(f'    <itemref idref="ch{i}"/>' for i in range(1, len(chapters) + 1))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<package version="3.0" unique-identifier="bookid" xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{escape(identifier)}</dc:identifier>
    <dc:title>{escape(book.title)}</dc:title>
    <dc:language>{escape(book.language)}</dc:language>
    <dc:creator>{escape(author)}</dc:creator>
    <meta property="dcterms:modified">{modified}</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="css" href="styles.css" media-type="text/css"/>
{chapter_items}
{image_items}
  </manifest>
  <spine toc="ncx">
{spine}
  </spine>
</package>"""
