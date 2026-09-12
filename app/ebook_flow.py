"""Telegram flow for e-reader downloads: pick a file, pick a device, pick a format.

Every step is an inline keyboard that edits the same message. The chosen device
is remembered per user so the next request is a single tap.
"""

import asyncio
import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.services.cache import CACHE
from app.services.ebook import DEVICES, UnsupportedSource, convert_to_ebook, get_device
from app.services.sources import (
    SourceUnavailable,
    fetch_source_file,
    list_sources,
    source_label,
)

LOGGER = logging.getLogger(__name__)

PREFIX = "eb"
SAVED_DEVICE_KEY = "ebook_device"
KOBO_DEVICES = {key for key in DEVICES if key.startswith(("clara", "libra", "sage", "elipsa"))}
CALLBACK_PATTERN = rf"^{PREFIX}\|"


def ebook_button(source_id: str) -> InlineKeyboardMarkup:
    """Button attached to every PDF/DOCX the bot sends."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📖 E-reader version (EPUB/KEPUB)", callback_data=f"{PREFIX}|s|{source_id}")
    ]])


async def ebook_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    sources = list_sources(context.application)
    keyboard = [[InlineKeyboardButton(s.label, callback_data=f"{PREFIX}|s|{s.id}")] for s in sources]
    await update.message.reply_text("Which file do you want for your e-reader?", reply_markup=InlineKeyboardMarkup(keyboard))


async def ebook_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or not query.data:
        return
    await query.answer()
    parts = query.data.split("|")
    step = parts[1] if len(parts) > 1 else ""

    if step == "s" and len(parts) == 3:
        await _ask_device(query, context, source_id=parts[2])
    elif step == "d" and len(parts) == 4:
        await _ask_format(query, context, source_id=parts[2], device_key=parts[3])
    elif step == "f" and len(parts) == 5:
        await _deliver(query, context, source_id=parts[2], device_key=parts[3], fmt=parts[4])
    elif step == "x":
        await query.edit_message_text("Cancelled.")


async def _ask_device(query, context, source_id: str):
    saved = context.user_data.get(SAVED_DEVICE_KEY)
    rows = []
    if saved in DEVICES:
        rows.append([InlineKeyboardButton(f"✅ {DEVICES[saved].name} (last used)", callback_data=f"{PREFIX}|d|{source_id}|{saved}")])
    rows += [
        [InlineKeyboardButton(device.label, callback_data=f"{PREFIX}|d|{source_id}|{device.key}")]
        for device in DEVICES.values()
    ]
    rows.append([InlineKeyboardButton("Cancel", callback_data=f"{PREFIX}|x")])
    label = source_label(context.application, source_id)
    await _show(query, f"{label}\n\nWhich device will you read it on? Images are sized for the screen you pick.", InlineKeyboardMarkup(rows))


async def _ask_format(query, context, source_id: str, device_key: str):
    if device_key not in DEVICES:
        await query.edit_message_text("Unknown device. Start again with /ebook.")
        return
    context.user_data[SAVED_DEVICE_KEY] = device_key
    if device_key not in KOBO_DEVICES:
        await _deliver(query, context, source_id, device_key, "epub")
        return
    rows = [
        [InlineKeyboardButton("KEPUB · Kobo native (recommended)", callback_data=f"{PREFIX}|f|{source_id}|{device_key}|kepub")],
        [InlineKeyboardButton("EPUB · standard", callback_data=f"{PREFIX}|f|{source_id}|{device_key}|epub")],
        [InlineKeyboardButton("Cancel", callback_data=f"{PREFIX}|x")],
    ]
    await _show(
        query,
        f"{source_label(context.application, source_id)} · {DEVICES[device_key].name}\n\n"
        "KEPUB uses Kobo's own reader (faster page turns, reading stats). EPUB works everywhere.",
        InlineKeyboardMarkup(rows),
    )


async def _deliver(query, context, source_id: str, device_key: str, fmt: str):
    device = get_device(device_key)
    label = source_label(context.application, source_id)
    await _show(query, f"Preparing {label} for {device.name} ({fmt.upper()})…", None)
    try:
        source_path = await fetch_source_file(context.application, source_id)
        author = os.getenv("EBOOK_AUTHOR", "Bukit Arang Church")
        book = await asyncio.to_thread(convert_to_ebook, source_path, device, fmt, author)
    except (SourceUnavailable, UnsupportedSource) as exc:
        await query.edit_message_text(str(exc))
        return
    except Exception as exc:
        LOGGER.exception("Ebook conversion failed for %s: %s", source_id, exc)
        await query.edit_message_text("Sorry, converting that file failed. Please try again later.")
        return

    cached_file_id = CACHE.get_file_id_for_name(book.cache_key)
    if cached_file_id:
        await query.message.reply_document(document=cached_file_id, filename=book.filename)
    else:
        with open(book.path, "rb") as fh:
            sent = await query.message.reply_document(document=fh, filename=book.filename)
        if sent.document:
            CACHE.set_file_id_for_name(book.cache_key, sent.document.file_id)
    await query.edit_message_text(f"{label} · {device.name} · {fmt.upper()}")


async def _show(query, text: str, markup: InlineKeyboardMarkup | None):
    """Edit the flow message in place; when the button lives on a document, start a new message."""
    if query.message is not None and query.message.text:
        await query.edit_message_text(text, reply_markup=markup)
    else:
        await query.message.reply_text(text, reply_markup=markup)
