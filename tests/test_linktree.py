from app.services.linktree import _extract_linktree_entries


def test_linktree_own_links_are_ignored():
    html = """
    <a href="https://drive.google.com/file/d/abc123/view">Sunday Gathering Bulletin</a>
    <a href="http://tiny.cc/owsongbook">Sing With Us</a>
    <a href="https://linktr.ee/privacy">Privacy</a>
    <a href="https://linktr.ee/blog/some-post">Blog post</a>
    <a href="https://sub.linktr.ee/x">Nested</a>
    """
    labels = [label for label, _ in _extract_linktree_entries(html)]
    assert labels == ["Sunday Gathering Bulletin", "Sing With Us"]
