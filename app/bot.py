import asyncio
import logging
import os

from telegram import BotCommand, BotCommandScopeChat, BotCommandScopeDefault, Update
from telegram.ext import CommandHandler, ContextTypes

from app.admin import admin_chat_id, is_admin_chat, send_to_admin
from app.ebook_flow import ebook_button
from app.services.cache import CACHE
from app.services.fetch import (
    Document,
    resolve_drive_document,
    resolve_outline_doc,
    resolve_outline_pdf,
    resolve_songbook,
)
from app.services.linktree import DriveLink, fetch_linktree, find_drive_links_async
from app.services.sources import drive_source_id

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DRIVE_LINK_REGISTRY_KEY = "drive_links"
DRIVE_LINK_HANDLERS_KEY = "drive_link_handlers"

STATIC_COMMANDS = [
    BotCommand("songbook", "The Open Worship songbook (PDF)"),
    BotCommand("outline", "This week's sermon outline (PDF)"),
    BotCommand("outline_doc", "This week's sermon outline (Word)"),
    BotCommand("ebook", "Any file as EPUB or KEPUB for an e-reader"),
    BotCommand("report", "Tell the maintainer something is broken"),
    BotCommand("help", "What this bot does and how to use it"),
    BotCommand("start", "Start the bot"),
]
ADMIN_COMMANDS = [
    BotCommand("refresh", "Re-read Linktree and rebuild the file commands"),
]
AWAITING_REPORT_KEY = "awaiting_report"


def _get_message(update: Update):
    if update.message is None:
        logger.warning("Received update without message payload.")
        return None
    return update.message


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _get_message(update)
    if message is None:
        return
    await message.reply_text(
        "Hi, I'm the Bukit Arang Bulletin Bot. I keep this week's Sunday bulletin, "
        "the songbook and the sermon outline one tap away, and I can turn any of them "
        "into an EPUB for your e-reader.\n\n"
        "Send /help to see everything I can do."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _get_message(update)
    if message is None:
        return

    lines = [
        "I fetch church files from the Bukit Arang Linktree and Google Drive so you don't have to hunt for them.",
        "",
        "Get a file",
    ]
    drive_links: dict[str, DriveLink] = context.application.bot_data.get(DRIVE_LINK_REGISTRY_KEY, {})
    lines += [f"/{link.command}: {link.label} (PDF)" for link in drive_links.values()]
    lines += [
        "/songbook: the Open Worship songbook (PDF)",
        "/outline: this week's sermon outline (PDF)",
        "/outline_doc: this week's sermon outline (Word)",
        "",
        "Read on a Kobo or other e-reader",
        "/ebook: pick a file and a device, get an EPUB or KEPUB sized for its screen. "
        "Every file I send also has an \"E-reader version\" button under it.",
        "",
        "Something wrong?",
        "/report followed by a short note, for example: /report the 2pm bulletin is last week's. "
        "It goes straight to the maintainer.",
    ]
    if is_admin_chat(message.chat_id):
        lines += ["", "Admin", "/refresh: re-read Linktree now and rebuild the file commands."]
    linktree_url = os.getenv("LINKTREE_URL", "")
    if linktree_url:
        lines += ["", f"Everything comes from {linktree_url}"]
    await message.reply_text("\n".join(lines))


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
    # Direct links and Telegram file ids belong to last week's files once Linktree changes.
    CACHE.clear_all()

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
    await application.bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    admin = admin_chat_id()
    if admin is not None:
        await application.bot.set_my_commands(commands + ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin))


async def set_bot_commands(application) -> None:
    await _set_bot_commands(application)


async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _get_message(update)
    if message is None:
        return
    if admin_chat_id() is not None and not is_admin_chat(message.chat_id):
        await message.reply_text(
            "Only the maintainer can run /refresh. Files refresh on their own every night; "
            "if something looks stale, send /report and say which file."
        )
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
        markup = ebook_button(drive_source_id(drive_link.command))
        if doc.telegram_ref:
            await message.reply_document(document=doc.telegram_ref, reply_markup=markup)
        elif doc.filepath:
            with open(doc.filepath, "rb") as fh:
                sent = await message.reply_document(document=fh, filename=doc.filename, reply_markup=markup)
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
        markup = ebook_button("songbook")
        if doc.telegram_ref:
            await message.reply_document(document=doc.telegram_ref, reply_markup=markup)
        elif doc.filepath:
            with open(doc.filepath, "rb") as fh:
                sent = await message.reply_document(document=fh, filename=doc.filename, reply_markup=markup)
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
            await message.reply_document(document=doc.telegram_ref, reply_markup=ebook_button("outline"))
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
        markup = ebook_button("outline")
        if doc.telegram_ref:
            await message.reply_document(document=doc.telegram_ref, reply_markup=markup)
        elif doc.filepath:
            with open(doc.filepath, "rb") as fh:
                sent = await message.reply_document(document=fh, filename=doc.filename, reply_markup=markup)
            if sent.document and doc.drive_file_id:
                CACHE.set_file_id_for_name(doc.filename, sent.document.file_id)
                CACHE.set_file_id_for_drive_id(doc.drive_file_id, sent.document.file_id)
        await status_message.delete()
    except Exception as exc:
        logger.error("Error in outline_doc command: %s", exc)
        await status_message.edit_text(
            "An error occurred while fetching the outline. Please try again later."
        )


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward a user's bug report to the admin chat, asking for details first if none were given."""
    message = _get_message(update)
    if message is None:
        return
    note = " ".join(context.args or []).strip()
    if not note:
        context.user_data[AWAITING_REPORT_KEY] = True
        await message.reply_text(
            "What went wrong? Reply with one message, for example: "
            "\"/bulletin gave me last week's file\" or \"the EPUB is missing page 3\"."
        )
        return
    await _forward_report(update, context, note)


async def capture_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Second half of /report: the next plain message from a user we asked for details."""
    message = _get_message(update)
    if message is None or not context.user_data.get(AWAITING_REPORT_KEY):
        return
    context.user_data[AWAITING_REPORT_KEY] = False
    await _forward_report(update, context, message.text or "")


async def _forward_report(update: Update, context: ContextTypes.DEFAULT_TYPE, note: str):
    message = update.message
    user = update.effective_user
    who = user.full_name if user else "unknown user"
    handle = f" @{user.username}" if user and user.username else ""
    user_id = user.id if user else "?"
    delivered = await send_to_admin(
        context.bot,
        f"Bug report from {who}{handle} (id {user_id}, chat {message.chat_id}):\n\n{note}",
    )
    if delivered:
        await message.reply_text("Thanks, your report has reached the maintainer.")
    else:
        await message.reply_text("I couldn't deliver your report right now. Please try again later.")
