from dataclasses import dataclass, field


@dataclass
class Asset:
    name: str          # file name inside OEBPS/images/
    media_type: str
    data: bytes


@dataclass
class Block:
    kind: str          # h1 | h2 | h3 | p | img
    html: str = ""     # inner XHTML for text blocks
    text: str = ""     # plain text, used for headings and de-duplication
    asset: Asset | None = None
    width_pct: int = 100
    # layout geometry in source-page points; used only while reading
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0
    size: float = 0.0
    bold: bool = False


@dataclass
class Book:
    title: str
    blocks: list[Block] = field(default_factory=list)
    assets: list[Asset] = field(default_factory=list)
    language: str = "en"
