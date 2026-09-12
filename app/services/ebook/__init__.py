"""Document-to-EPUB/KEPUB conversion for e-readers.

The device profiles, reflowable stylesheet and package layout are adapted from
KoboForge by Alphaeus Ng (https://github.com/AlphaeusNg/KoboForge, MIT). The PDF
reader is our own: it works from PyMuPDF's font-aware line geometry, keeps
hyperlinks and embedded images, and renders pages that carry no extractable text
as images instead of dropping them.
"""

from app.services.ebook.convert import ConvertedBook, UnsupportedSource, convert_to_ebook
from app.services.ebook.devices import DEVICES, DeviceProfile, get_device

__all__ = [
    "ConvertedBook",
    "DEVICES",
    "DeviceProfile",
    "UnsupportedSource",
    "convert_to_ebook",
    "get_device",
]
