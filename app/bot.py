import asyncio
import logging
import os

from telegram import BotCommand, Update
from telegram.ext import CommandHandler, ContextTypes

from app.services.cache import CACHE
from app.services.fetch import (
    Document,
    resolve_drive_document,
    resolve_outline_doc,
    resolve_outline_pdf,
    resolve_songbook,
)
from app.services.linktree import DriveLink, fetch_linktree, find_drive_links_async

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DRIVE_LINK_REGISTRY_KEY = "drive_links"
DRIVE_LINK_HANDLERS_KEY = "drive_link_handlers"

STATIC_COMMANDS = [
    BotCommand("songbook", "Download the latest Songbook"),
    BotCommand("outline", "Download the Sermon Outline (PDF)"),
    BotCommand("outline_doc", "Download the Sermon Outline (DOCX)"),
    BotCommand("help", "Show available commands"),
    BotCommand("start", "Start the bot"),
]


def _get_message(update: Update):
    if update.message is None:
        logger.warning("Received update without message payload.")
        return None
    return update.message


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _get_message(update)
    if message is None:
        return

    linktree_url = os.getenv("LINKTREE_URL", "")
    linktree_text = f"\nVisit our Linktree: {linktree_url}" if linktree_url else ""
    await message.reply_text(
        text=f"Hi! I'm the Bukit Arang Bulletin Bot.\n"
        f"Use /refresh to fetch the latest file commands.\n"
        f"Use /songbook to get the latest Songbook.\n"
        f"Use /outline for the Sermon Outline (PDF).\n"
        f"Use /outline_doc for the Sermon Outline (DOCX).{linktree_text}"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _get_message(update)
    if message is None:
        return

    linktree_url = os.getenv("LINKTREE_URL", "")
    linktree_text = f"\nLinktree: {linktree_url}" if linktree_url else ""
    drive_link_commands = _format_drive_link_commands(context)
    await message.reply_text(
        f"Available commands:\n"
        f"/start - Start the bot\n"
        f"/refresh - Refresh file commands from Linktree\n"
        f"{drive_link_commands}"
        f"/songbook - Download the latest Songbook\n"
        f"/outline - Download the Sermon Outline (PDF)\n"
        f"/outline_doc - Download the Sermon Outline (DOCX)\n"
        f"/help - Show this help message{linktree_text}"
    )


def _format_drive_link_commands(context: ContextTypes.DEFAULT_TYPE) -> str:
    drive_links: dict[str, DriveLink] = context.application.bot_data.get(
        DRIVE_LINK_REGISTRY_KEY,
        {},
    )
    if not drive_links:
        return ""
    return "".join(
        f"/{drive_link.command} - Download {drive_link.label}\n"
        for drive_link in drive_links.values()
    )


async def refresh_drive_link_commands(application) -> list[DriveLink]:
    """Fetch Linktree, rebuild Drive file commands, and update Telegram suggestions."""
    html = await asyncio.to_thread(fetch_linktree, force=True)
    reserved_commands = {command.command for command in STATIC_COMMANDS}
    drive_links = [
        link for link in await find_drive_links_async(html)
        if link.command not in reserved_commands
    ]

    for handler in application.bot_data.get(DRIVE_LINK_HANDLERS_KEY, []):
        application.remove_handler(handler)

    handlers = []
    registry = {drive_link.command: drive_link for drive_link in drive_links}
    for drive_link in drive_links:
        handler = CommandHandler(drive_link.command, dynamic_drive_link)
        application.add_handler(handler)
        handlers.append(handler)

    application.bot_data[DRIVE_LINK_REGISTRY_KEY] = registry
    application.bot_data[DRIVE_LINK_HANDLERS_KEY] = handlers
    await _set_bot_commands(application)
    return drive_links


refresh_bulletin_commands = refresh_drive_link_commands


async def _set_bot_commands(application) -> None:
    drive_links: dict[str, DriveLink] = application.bot_data.get(
        DRIVE_LINK_REGISTRY_KEY,
        {},
    )
    commands = [
        BotCommand(
            drive_link.command,
            f"Download {drive_link.label}"[:256],
        )
        for drive_link in drive_links.values()
    ]
    commands.extend(STATIC_COMMANDS)
    await application.bot.set_my_commands(commands)


async def set_bot_commands(application) -> None:
    await _set_bot_commands(application)


async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _get_message(update)
    if message is None:
        return

    status_message = await message.reply_text("Refreshing file commands from Linktree...")
    try:
        drive_links = await refresh_drive_link_commands(context.application)
        if not drive_links:
            await status_message.edit_text(
                "Refresh complete, but no Google Drive-backed file links were found."
            )
            return

        command_list = "\n".join(
            f"/{drive_link.command} - {drive_link.label}" for drive_link in drive_links
        )
        await status_message.edit_text(
            f"Refresh complete. Available file commands:\n{command_list}"
        )
    except Exception as exc:
        logger.error("Error refreshing file commands: %s", exc)
        await status_message.edit_text(
            "An error occurred while refreshing file commands. Please try again later."
        )


async def dynamic_drive_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _get_message(update)
    if message is None or not message.text:
        return

    command = message.text.split()[0].split("@")[0].lstrip("/")
    drive_links: dict[str, DriveLink] = context.application.bot_data.get(
        DRIVE_LINK_REGISTRY_KEY,
        {},
    )
    drive_link = drive_links.get(command)
    if not drive_link:
        await message.reply_text(
            "I don't have that file command loaded. Use /refresh and try again."
        )
        return

    await _send_drive_link(update, drive_link)


async def _send_drive_link(update: Update, drive_link: DriveLink):
    message = _get_message(update)
    if message is None:
        return

    status_message = await message.reply_text(f"Fetching {drive_link.label}... please wait.")
    try:
        doc = await resolve_drive_document(drive_link, CACHE)
        if not doc.found:
            await status_message.edit_text(
                f"Sorry, I couldn't prepare '{drive_link.label}' for download."
            )
            return

        await status_message.edit_text(f"Sending {drive_link.label}...")
        if doc.telegram_ref:
            await message.reply_document(document=doc.telegram_ref)
        elif doc.filepath:
            with open(doc.filepath, "rb") as fh:
                sent = await message.reply_document(document=fh, filename=doc.filename)
            if sent.document and doc.drive_file_id:
                CACHE.set_file_id_for_drive_id(doc.drive_file_id, sent.document.file_id)
                CACHE.set_file_id_for_url(drive_link.url, sent.document.file_id)
        await status_message.delete()
    except Exception as exc:
        logger.error("Error sending dynamic file '%s': %s", drive_link.label, exc)
        await status_message.edit_text(
            "An error occurred while fetching the file. Please try again later."
        )


async def songbook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _get_message(update)
    if message is None:
        return

    status_message = await message.reply_text("Fetching the latest songbook...")
    try:
        doc = await resolve_songbook(CACHE)
        if not doc.found:
            await status_message.edit_text("Sorry, I couldn't find the 'Songbook'.")
            return

        await status_message.edit_text("Sending songbook...")
        if doc.telegram_ref:
            await message.reply_document(document=doc.telegram_ref)
        elif doc.filepath:
            with open(doc.filepath, "rb") as fh:
                sent = await message.reply_document(document=fh, filename=doc.filename)
            if sent.document and doc.source_url:
                CACHE.set_file_id_for_name(doc.filename, sent.document.file_id)
                CACHE.set_file_id_for_url(doc.source_url, sent.document.file_id)
        await status_message.delete()
    except Exception as exc:
        logger.error("Error in songbook command: %s", exc)
        await status_message.edit_text(
            "An error occurred while fetching the songbook. Please try again later."
        )


async def outline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _get_message(update)
    if message is None:
        return

    status_message = await message.reply_text("Fetching the sermon outline (PDF)... please wait.")
    try:
        doc = await resolve_outline_pdf(CACHE)
        if not doc.found:
            await status_message.edit_text("Sorry, I couldn't find the sermon outline (PDF).")
            return

        await status_message.edit_text("Sending sermon outline (PDF)...")
        try:
            await message.reply_document(document=doc.telegram_ref)
            await status_message.delete()
        except Exception as exc:
            logger.error("Failed to send outline link: %s", exc)
            await status_message.edit_text(
                "An error occurred while fetching the outline. Please try again later."
            )
    except Exception as exc:
        logger.error("Error in outline command: %s", exc)
        await status_message.edit_text(
            "An error occurred while fetching the outline. Please try again later."
        )


async def outline_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _get_message(update)
    if message is None:
        return

    status_message = await message.reply_text("Fetching the sermon outline (DOC)... please wait.")
    try:
        doc = await resolve_outline_doc(CACHE)
        if not doc.found:
            await status_message.edit_text("Sorry, I could not find the sermon outline (DOC).")
            return

        await status_message.edit_text("Sending sermon outline (DOC)...")
        if doc.telegram_ref:
            await message.reply_document(document=doc.telegram_ref)
        elif doc.filepath:
            with open(doc.filepath, "rb") as fh:
                sent = await message.reply_document(document=fh, filename=doc.filename)
            if sent.document and doc.drive_file_id:
                CACHE.set_file_id_for_name(doc.filename, sent.document.file_id)
                CACHE.set_file_id_for_drive_id(doc.drive_file_id, sent.document.file_id)
        await status_message.delete()
    except Exception as exc:
        logger.error("Error in outline_doc command: %s", exc)
        await status_message.edit_text(
            "An error occurred while fetching the outline. Please try again later."
        )
