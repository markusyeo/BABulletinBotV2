import pymupdf
import pytest


@pytest.fixture
def bulletin_pdf(tmp_path):
    """A two-page PDF shaped like the church bulletin: section header, label column, body column."""
    doc = pymupdf.open()
    for page_no in range(2):
        page = doc.new_page(width=420, height=595)
        page.insert_text((42, 40), "ORDER OF GATHERING", fontsize=10, fontname="hebo")
        page.insert_text((42, 100), "Call to Worship", fontsize=11, fontname="helv")
        page.insert_text((164, 100), "Begins our gathering. God calls us to", fontsize=9.5, fontname="heit")
        page.insert_text((164, 112), "worship him and we respond.", fontsize=9.5, fontname="heit")
        page.insert_text((164, 132), "Romans 4:16-17", fontsize=10.5, fontname="hebo")
        page.insert_text((164, 146), "Elder Someone", fontsize=10, fontname="heit")
        page.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(164, 136, 240, 150), "uri": "http://tiny.cc/example"})
        page.insert_text((385, 570), str(page_no + 1), fontsize=9.5)
    path = tmp_path / "bulletin.pdf"
    doc.save(path)
    doc.close()
    return str(path)


@pytest.fixture
def scanned_pdf(tmp_path):
    """A PDF whose only content is a picture: no extractable text at all."""
    doc = pymupdf.open()
    page = doc.new_page(width=420, height=595)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 300), False)
    pix.clear_with(90)
    page.insert_image(pymupdf.Rect(40, 40, 380, 550), pixmap=pix)
    path = tmp_path / "scan.pdf"
    doc.save(path)
    doc.close()
    return str(path)
