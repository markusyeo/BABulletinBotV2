import json

from app.services import outlines, sources
from app.services.drive import FOLDER_MIME, extract_outline_file_id, list_folder_items

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _folder_html(items):
    rows = [[file_id, ["parent"], name, mime] for file_id, name, mime in items]
    return f"<script>window['_DRIVE_ivd'] = '{json.dumps([rows])}';</script>"


def test_folder_items_and_file_lookup():
    html = _folder_html([("f1", "a.docx", DOCX), ("f2", "a.pdf", "application/pdf")])
    assert list_folder_items(html) == [("f1", "a.docx", DOCX), ("f2", "a.pdf", "application/pdf")]
    assert extract_outline_file_id(html, "application/pdf") == "f2"
    assert extract_outline_file_id(html, "msword") is None
    assert list_folder_items("<html>no data</html>") == []


def test_slugs_match_bulletin_commands():
    assert outlines.service_slug("830/1045am") == "830_1045am"
    assert outlines.service_slug("8.30/10.45am") == "830_1045am"
    assert outlines.service_slug("2pm") == "2pm"
    assert outlines.service_label("830/1045am") == "8.30/10.45am"
    assert outlines.service_label("2pm") == "2pm"


def test_discover_split_folder_sorts_morning_first(monkeypatch):
    html = _folder_html([("pm", "2pm", FOLDER_MIME), ("am", "830/1045am", FOLDER_MIME)])
    monkeypatch.setattr(outlines, "fetch_drive_folder", lambda url=None: html)
    services = outlines.discover_outline_services("https://root")
    assert [(s.slug, s.label) for s in services] == [("830_1045am", "8.30/10.45am"), ("2pm", "2pm")]
    assert services[0].folder_url == "https://drive.google.com/drive/folders/am"
    assert services[1].title == "Sermon Outline (2pm)"


def test_discover_flat_folder_is_one_gathering(monkeypatch):
    html = _folder_html([("f1", "outline.docx", DOCX)])
    monkeypatch.setattr(outlines, "fetch_drive_folder", lambda url=None: html)
    [service] = outlines.discover_outline_services("https://root")
    assert (service.slug, service.title, service.folder_url) == ("", "Sermon Outline", "https://root")
    assert outlines.outline_source_id(service.slug) == "outline"


def test_ebook_sources_list_each_gathering():
    class App:
        bot_data = {outlines.OUTLINE_REGISTRY_KEY: {
            "830_1045am": outlines.OutlineService("830_1045am", "8.30/10.45am", "u1"),
            "2pm": outlines.OutlineService("2pm", "2pm", "u2"),
        }}

    ids = [source.id for source in sources.list_sources(App())]
    assert ids[-2:] == ["o:830_1045am", "o:2pm"]
