import xml.dom.minidom
import zipfile

import pytest

from app.services.ebook import UnsupportedSource, convert_to_ebook, get_device
from app.services.ebook.pdf_reader import read_pdf


def _xml_ok(archive: zipfile.ZipFile) -> None:
    for name in archive.namelist():
        if name.endswith((".xhtml", ".opf", ".ncx", ".xml")):
            xml.dom.minidom.parseString(archive.read(name))


def test_bulletin_layout_becomes_headings_labels_and_links(bulletin_pdf):
    book = read_pdf(bulletin_pdf, get_device("libra-colour"), "bulletin")
    kinds = [b.kind for b in book.blocks]
    assert kinds.count("h1") == 1, "the repeated section header is kept once"
    assert "h3" in kinds, "the left-hand label column becomes sub-headings"
    assert not any(b.text in ("1", "2") for b in book.blocks), "page numbers are dropped"
    joined = " ".join(b.html for b in book.blocks)
    assert 'href="http://tiny.cc/example"' in joined
    assert "God calls us to worship him" in " ".join(b.text for b in book.blocks), "wrapped lines are joined"


def test_epub_and_kepub_are_well_formed_and_cached(bulletin_pdf, tmp_path):
    cache = str(tmp_path / "cache")
    epub = convert_to_ebook(bulletin_pdf, get_device("clara-bw"), "epub", "Test", cache_dir=cache)
    kepub = convert_to_ebook(bulletin_pdf, get_device("clara-bw"), "kepub", "Test", cache_dir=cache)
    assert epub.filename.endswith(".epub") and kepub.filename.endswith(".kepub.epub")
    assert epub.path != kepub.path

    with zipfile.ZipFile(epub.path) as zf:
        assert zf.namelist()[0] == "mimetype"
        assert zf.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        _xml_ok(zf)
        assert "koboSpan" not in zf.read("OEBPS/chapter-1.xhtml").decode()
    with zipfile.ZipFile(kepub.path) as zf:
        _xml_ok(zf)
        chapter = zf.read("OEBPS/chapter-1.xhtml").decode()
        assert 'id="book-inner"' in chapter and 'class="koboSpan" id="kobo.1.1"' in chapter

    again = convert_to_ebook(bulletin_pdf, get_device("clara-bw"), "epub", "Test", cache_dir=cache)
    assert again.path == epub.path


def test_scanned_pdf_pages_are_kept_as_images(scanned_pdf, tmp_path):
    book = read_pdf(scanned_pdf, get_device("libra-colour"), "scan")
    assert [b.kind for b in book.blocks] == ["img"]
    assert book.assets and book.assets[0].data
    result = convert_to_ebook(scanned_pdf, get_device("libra-colour"), "epub", "Test", cache_dir=str(tmp_path))
    with zipfile.ZipFile(result.path) as zf:
        assert any(n.startswith("OEBPS/images/") for n in zf.namelist())


def test_unsupported_extension_is_rejected(tmp_path):
    legacy = tmp_path / "outline.doc"
    legacy.write_bytes(b"not really a word file")
    with pytest.raises(UnsupportedSource):
        convert_to_ebook(str(legacy), get_device("sage"), "epub", "Test", cache_dir=str(tmp_path))


def test_large_vertical_gaps_become_note_space(tmp_path):
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((36, 60), "Applications", fontsize=12, fontname="hebo")
    page.insert_text((36, 260), "Discussion questions", fontsize=12, fontname="hebo")
    page.insert_text((36, 285), "1. What does trusting God look like for you?", fontsize=12, fontname="helv")
    path = tmp_path / "outline.pdf"
    doc.save(path)
    doc.close()

    book = read_pdf(str(path), get_device("libra-colour"), "outline")
    kinds = [b.kind for b in book.blocks]
    assert kinds.count("space") == 1, kinds
    space = next(b for b in book.blocks if b.kind == "space")
    assert 4 <= space.height_em <= 12
