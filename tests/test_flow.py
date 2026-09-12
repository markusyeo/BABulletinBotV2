from app.bot import DRIVE_LINK_REGISTRY_KEY
from app.ebook_flow import DEVICES, PREFIX, ebook_button
from app.services import sources


def test_registry_key_shared_between_bot_and_sources():
    assert sources.DRIVE_LINK_REGISTRY_KEY == DRIVE_LINK_REGISTRY_KEY


def test_callback_data_fits_telegram_limit():
    longest_source = sources.drive_source_id("x" * 32)
    for device in DEVICES.values():
        data = f"{PREFIX}|f|{longest_source}|{device.key}|kepub"
        assert len(data.encode()) <= 64, data


def test_button_targets_source():
    markup = ebook_button("songbook")
    assert markup.inline_keyboard[0][0].callback_data == "eb|s|songbook"
