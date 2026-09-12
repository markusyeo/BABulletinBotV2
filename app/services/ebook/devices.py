"""E-reader screen profiles.

Kobo figures (portrait pixels and PPI) come from KoboForge's device table by
Alphaeus Ng (https://github.com/AlphaeusNg/KoboForge, MIT).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceProfile:
    key: str
    name: str
    short: str
    screen_width: int
    screen_height: int
    ppi: int
    colour: bool

    @property
    def label(self) -> str:
        tone = "colour" if self.colour else "B&W"
        return f"{self.name} · {self.short} {tone}"


DEVICES: dict[str, DeviceProfile] = {
    d.key: d
    for d in (
        DeviceProfile("clara-bw", "Kobo Clara BW", '6"', 1072, 1448, 300, False),
        DeviceProfile("clara-colour", "Kobo Clara Colour", '6"', 1072, 1448, 300, True),
        DeviceProfile("libra-colour", "Kobo Libra Colour", '7"', 1264, 1680, 300, True),
        DeviceProfile("sage", "Kobo Sage", '8"', 1440, 1920, 300, False),
        DeviceProfile("elipsa-2e", "Kobo Elipsa 2E", '10.3"', 1404, 1872, 227, False),
        DeviceProfile("kindle", "Kindle or similar reader", '6"', 1072, 1448, 300, False),
        DeviceProfile("phone", "Phone or tablet", "", 1080, 1920, 400, True),
    )
}

DEFAULT_DEVICE = "libra-colour"


def get_device(key: str | None) -> DeviceProfile:
    return DEVICES.get(key or "", DEVICES[DEFAULT_DEVICE])
