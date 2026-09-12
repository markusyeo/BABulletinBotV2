"""Turn a PDF into a stream of headings, paragraphs and images.

Strategy: PyMuPDF gives us every text line with its font, size, weight and
position. Lines are merged into paragraphs by proximity, headings are picked by
size and weight relative to the document's body text, and a per-page layout pass
recognises the two-column "label | body" pattern that bulletins use. Pages with
no extractable text (scans, flattened designs) are rendered to an image so
nothing silently disappears.
"""

import logging
import re
import statistics
from html import escape

import pymupdf

from app.services.ebook.devices import DeviceProfile
from app.services.ebook.model import Asset, Block, Book

LOGGER = logging.getLogger(__name__)

BOLD_FLAG = 16
ITALIC_FLAG = 2
SUPERSCRIPT_FLAG = 1
MIN_IMAGE_POINTS = 14         # displayed size below this is decoration (icons, bullets)
LABEL_ZONE_RATIO = 0.3        # left 30% of the page may hold labels
HEADING_SCALE = 1.25          # size relative to body text that makes a heading
IMAGE_MIN_WIDTH_PCT = 30
JPEG_PIXEL_THRESHOLD = 300_000


def read_pdf(path: str, device: DeviceProfile, title: str) -> Book:
    doc = pymupdf.open(path)
    try:
        book = Book(title=(doc.metadata or {}).get("title") or title)
        pages = [_page_lines(page) for page in doc]
        body_size = _body_size(pages)
        image_counter = [0]
        for page, lines in zip(doc, pages):
            blocks = _page_blocks(page, lines, body_size, device, book.assets, image_counter)
            book.blocks.extend(blocks)
        _drop_repeated_section_headers(book.blocks)
        return book
    finally:
        doc.close()


# --- line extraction ---------------------------------------------------------

class _Line:
    __slots__ = ("x0", "y0", "x1", "y1", "size", "bold", "italic", "text", "html")

    def __init__(self, x0, y0, x1, y1, size, bold, italic, text, html):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.size, self.bold, self.italic = size, bold, italic
        self.text, self.html = text, html


def _page_lines(page: pymupdf.Page) -> list[_Line]:
    links = [(pymupdf.Rect(l["from"]), l["uri"]) for l in page.get_links() if l.get("uri")]
    lines: list[_Line] = []
    data = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
    for block in data["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            text = "".join(s["text"] for s in line["spans"]).strip()
            main = max(spans, key=lambda s: len(s["text"]))
            lines.append(_Line(
                *line["bbox"],
                size=round(main["size"], 1),
                bold=_is_bold(main),
                italic=_is_italic(main),
                text=text,
                html=_spans_html(line["spans"], links),
            ))
    return lines


def _is_bold(span: dict) -> bool:
    font = span["font"].lower()
    return bool(span["flags"] & BOLD_FLAG) or any(w in font for w in ("bold", "semibold", "black", "heavy"))


def _is_italic(span: dict) -> bool:
    font = span["font"].lower()
    return bool(span["flags"] & ITALIC_FLAG) or "italic" in font or "oblique" in font


def _spans_html(spans: list[dict], links: list[tuple[pymupdf.Rect, str]]) -> str:
    parts: list[str] = []
    for span in spans:
        text = span["text"]
        if not text:
            continue
        html = escape(text)
        if span["flags"] & SUPERSCRIPT_FLAG:
            html = f"<sup>{html}</sup>"
        if _is_bold(span):
            html = f"<strong>{html}</strong>"
        if _is_italic(span):
            html = f"<em>{html}</em>"
        href = _link_for(pymupdf.Rect(span["bbox"]), links)
        if href:
            html = f'<a href="{escape(href, quote=True)}">{html}</a>'
        parts.append(html)
    return "".join(parts).strip()


def _link_for(rect: pymupdf.Rect, links: list[tuple[pymupdf.Rect, str]]) -> str | None:
    for area, uri in links:
        overlap = rect & area
        if not overlap.is_empty and overlap.get_area() > 0.5 * rect.get_area():
            return uri
    return None


def _body_size(pages: list[list[_Line]]) -> float:
    sizes: list[float] = []
    for lines in pages:
        for line in lines:
            sizes.extend([line.size] * len(line.text))
    return statistics.median(sizes) if sizes else 10.0


# --- paragraph assembly ------------------------------------------------------

def _merge_lines(lines: list[_Line]) -> list[Block]:
    """Join consecutive lines into paragraphs; keep bold/italic runs intact."""
    paragraphs: list[Block] = []
    open_lines: list[list[_Line]] = []
    for line in sorted(lines, key=lambda l: (round(l.y0), l.x0)):
        target = None
        for group in open_lines:
            last = group[-1]
            gap = line.y0 - last.y1
            same_size = abs(line.size - last.size) <= 0.6
            overlaps_x = line.x0 < last.x1 and line.x1 > last.x0
            if same_size and overlaps_x and -0.2 * line.size <= gap <= 0.7 * line.size:
                target = group
                break
        if target is None:
            open_lines.append([line])
        else:
            target.append(line)

    for group in open_lines:
        paragraphs.append(Block(
            kind="p", html=_join_html(group), text=_join_text([l.text for l in group]),
            x0=min(l.x0 for l in group), y0=min(l.y0 for l in group),
            x1=max(l.x1 for l in group), y1=max(l.y1 for l in group),
            size=group[0].size,
            bold=group[0].bold,
        ))
    return paragraphs


def _join_html(group: list[_Line]) -> str:
    """Join lines with a space where the text wraps, and a line break where it does not.

    A break is kept when the style changes (title over presenter name), when both
    lines are bold (stacked titles), or when a short line ends without a
    continuation mark and the next starts a new sentence.
    """
    widest = max(l.x1 - l.x0 for l in group)
    verse_like = _looks_like_verse(group)
    out = group[0].html
    for previous, line in zip(group, group[1:]):
        style_changed = (previous.bold, previous.italic) != (line.bold, line.italic)
        short_line = (previous.x1 - previous.x0) < 0.6 * widest
        fresh_start = line.text[:1].isupper() and not previous.text.endswith((",", ";", "-", "and", "or", "the", "to", "of"))
        if verse_like or style_changed or (previous.bold and line.bold) or (short_line and fresh_start):
            out += "<br/>" + line.html
        elif out.endswith("-</em>") or out.endswith("-</strong>") or out.endswith("-"):
            out += line.html
        else:
            out += " " + line.html
    return _merge_adjacent_tags(out)


def _looks_like_verse(group: list[_Line]) -> bool:
    """Song lyrics and poetry: most lines start capitalised and few end in sentence punctuation."""
    if len(group) < 3:
        return False
    capitalised = sum(l.text[:1].isupper() for l in group)
    terminated = sum(l.text.rstrip().endswith((".", "!", "?", ":")) for l in group)
    return capitalised >= 0.8 * len(group) and terminated <= 0.2 * len(group)


def _merge_adjacent_tags(html: str) -> str:
    for tag in ("em", "strong"):
        html = html.replace(f"</{tag}> <{tag}>", " ").replace(f"</{tag}><br/><{tag}>", "<br/>")
    return html


def _join_text(pieces: list[str]) -> str:
    out = ""
    for piece in pieces:
        if out.endswith("-") and piece[:1].islower():
            out = out[:-1] + piece
        elif out:
            out += " " + piece
        else:
            out = piece
    return out


# --- classification and page layout -----------------------------------------

def _classify(block: Block, body_size: float) -> None:
    words = block.text.split()
    letters = [c for c in block.text if c.isalpha()]
    all_caps = bool(letters) and all(c.isupper() for c in letters)
    if all_caps and len(words) <= 6 and block.bold and block.size >= 0.9 * body_size:
        block.kind = "h1"
    elif block.size >= HEADING_SCALE * body_size and len(words) <= 12:
        block.kind = "h2"


def _page_blocks(
    page: pymupdf.Page,
    lines: list[_Line],
    body_size: float,
    device: DeviceProfile,
    assets: list[Asset],
    counter: list[int],
) -> list[Block]:
    width, height = page.rect.width, page.rect.height
    texts = [b for b in _merge_lines(lines) if not _is_page_number(b, height)]
    if not texts:
        image = _render_region(page, page.rect, device, 100, assets, counter)
        return [image] if image else []

    for block in texts:
        _classify(block, body_size)

    images = _page_images(page, device, assets, counter)
    label_zone = width * LABEL_ZONE_RATIO
    right_texts = [b for b in texts if b.x0 >= label_zone]
    for block in texts:
        if block.kind == "p" and block.x0 < label_zone and len(block.text.split()) <= 6:
            if any(r.x0 > block.x1 + 4 and _overlap_y(block, r) > 0 for r in right_texts):
                block.kind = "h3"

    has_left_anchor = any(b.kind == "h3" for b in texts) or any(i.x0 < label_zone for i in images)
    if not has_left_anchor:
        return sorted(texts + images, key=lambda b: (b.y0, b.x0))

    anchors = sorted(
        [b for b in texts if b.x0 < label_zone] + images,
        key=lambda b: (b.y0, b.x0),
    )
    attached: dict[int, list[Block]] = {i: [] for i in range(len(anchors))}
    leading: list[Block] = []
    for block in sorted(right_texts, key=lambda b: (b.y0, b.x0)):
        owner = None
        for index, anchor in enumerate(anchors):
            if anchor.y0 - 0.6 * block.size <= block.y0:
                owner = index
        (attached[owner] if owner is not None else leading).append(block)

    ordered = list(leading)
    for index, anchor in enumerate(anchors):
        ordered.append(anchor)
        ordered.extend(attached[index])
    return ordered


def _is_page_number(block: Block, page_height: float) -> bool:
    return block.text.isdigit() and len(block.text) <= 3 and block.y0 > 0.88 * page_height


def _overlap_y(a: Block, b: Block) -> float:
    return min(a.y1, b.y1) - max(a.y0, b.y0)


def _drop_repeated_section_headers(blocks: list[Block]) -> None:
    """Bulletins repeat the section title on every page; keep the first only."""
    current = None
    for block in list(blocks):
        if block.kind == "h1":
            if block.text == current:
                blocks.remove(block)
            current = block.text


# --- images ------------------------------------------------------------------

def _page_images(
    page: pymupdf.Page, device: DeviceProfile, assets: list[Asset], counter: list[int]
) -> list[Block]:
    blocks: list[Block] = []
    seen: set[tuple[int, int, int, int]] = set()
    for info in page.get_image_info(xrefs=True):
        rect = pymupdf.Rect(info["bbox"]) & page.rect
        if rect.is_empty or rect.width < MIN_IMAGE_POINTS or rect.height < MIN_IMAGE_POINTS:
            continue
        key = tuple(int(v) for v in rect)
        if key in seen:
            continue
        seen.add(key)
        pct = max(IMAGE_MIN_WIDTH_PCT, min(100, round(rect.width / page.rect.width * 100)))
        block = _render_region(page, rect, device, pct, assets, counter)
        if block:
            blocks.append(block)
    return blocks


def _render_region(
    page: pymupdf.Page,
    rect: pymupdf.Rect,
    device: DeviceProfile,
    width_pct: int,
    assets: list[Asset],
    counter: list[int],
) -> Block | None:
    target_px = device.screen_width * width_pct / 100
    zoom = min(target_px / rect.width, 4.0)
    colorspace = pymupdf.csRGB if device.colour else pymupdf.csGRAY
    try:
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=rect, colorspace=colorspace, alpha=False)
    except Exception as exc:
        LOGGER.warning("Could not render PDF region on page %s: %s", page.number + 1, exc)
        return None
    if pix.width * pix.height > JPEG_PIXEL_THRESHOLD:
        data, ext, media = pix.tobytes("jpeg", jpg_quality=80), "jpg", "image/jpeg"
    else:
        data, ext, media = pix.tobytes("png"), "png", "image/png"
    counter[0] += 1
    asset = Asset(name=f"img{counter[0]:03d}.{ext}", media_type=media, data=data)
    assets.append(asset)
    return Block(kind="img", asset=asset, width_pct=width_pct, x0=rect.x0, y0=rect.y0, x1=rect.x1, y1=rect.y1)
