import asyncio
import logging
import os
import re

from telegram import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyParameters,
    Update,
)
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
from app.services.outlines import (
    OUTLINE_REGISTRY_KEY,
    OutlineService,
    discover_outline_services_async,
    outline_source_id,
)
from app.services.sources import drive_source_id

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DRIVE_LINK_REGISTRY_KEY = "drive_links"
DRIVE_LINK_HANDLERS_KEY = "drive_link_handlers"
OUTLINE_KINDS = {"pdf": "PDF", "doc": "Word"}
# Gathering picker shown by /bulletin and /outline when the gatherings have different files.
PICK_PREFIX = "pk"
PICK_PATTERN = rf"^{PICK_PREFIX}\|"
PICK_ALL = "*"
BULLETIN_KIND = "b"

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
    BotCommand("stats", "How many people use the bot"),
    BotCommand("announce", "Message everyone who uses the bot"),
]
AWAITING_REPORT_KEY = "awaiting_report"
# Parsed back out of a forwarded report when the admin replies to it, so answers survive restarts.
# Reports sent before "msg" was added still carry the chat id.
REPORT_HEADER = re.compile(r"^Bug report from .*\(id [^,]+, chat (-?\d+)(?:, msg (\d+))?\):", re.MULTILINE)


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
    bulletins = bulletin_links(context.application)
    if len(bulletins) > 1:
        lines.append(f"/bulletin: this week's bulletin (PDF). I'll ask which gathering: "
                     f"{' or '.join(gathering_label(link.label) for link in bulletins)}.")
    elif bulletins:
        lines.append("/bulletin: this week's bulletin (PDF)")
    lines += [f"/{link.command}: {link.label} (PDF)" for link in other_drive_links(context.application)]
    lines += [
        "/songbook: the Open Worship songbook (PDF)",
        "/outline: this week's sermon outline (PDF)",
        "/outline_doc: this week's sermon outline (Word)",
        "When the gatherings have different bulletins or outlines, I'll ask which one you want.",
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
        lines += [
            "", "Admin",
            "/refresh: re-read Linktree now and rebuild the file commands.",
            "/stats: how many people use the bot, and which commands.",
            "/announce followed by a message: preview it, then send it to everyone who uses the bot.",
            "Reply to a bug report here and I'll send your reply to the person who reported it.",
        ]
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
    try:
        await refresh_outline_services(application)
    except Exception as exc:
        # Keep last week's gatherings; /outline and /outline_doc still look the folder up live.
        logger.error("Failed to refresh outline gatherings: %s", exc)
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
        if is_bulletin(drive_link):
            continue  # every bulletin is reached through /bulletin, which asks for the gathering
        handler = CommandHandler(drive_link.command, dynamic_drive_link)
        application.add_handler(handler)
        handlers.append(handler)

    application.bot_data[DRIVE_LINK_REGISTRY_KEY] = registry
    application.bot_data[DRIVE_LINK_HANDLERS_KEY] = handlers
    await _set_bot_commands(application)
    return drive_links


refresh_bulletin_commands = refresh_drive_link_commands


async def refresh_outline_services(application) -> list[OutlineService]:
    """Remember this week's outline gatherings, for the e-reader file list and refresh summaries."""
    services = await discover_outline_services_async()
    application.bot_data[OUTLINE_REGISTRY_KEY] = {service.slug: service for service in services}
    return services


def is_bulletin(drive_link: DriveLink) -> bool:
    return "bulletin" in drive_link.label.lower()


def bulletin_links(application) -> list[DriveLink]:
    drive_links: dict[str, DriveLink] = application.bot_data.get(DRIVE_LINK_REGISTRY_KEY, {})
    return [link for link in drive_links.values() if is_bulletin(link)]


def other_drive_links(application) -> list[DriveLink]:
    drive_links: dict[str, DriveLink] = application.bot_data.get(DRIVE_LINK_REGISTRY_KEY, {})
    return [link for link in drive_links.values() if not is_bulletin(link)]


def gathering_label(label: str) -> str:
    """"8.30/10.45am Gathering Bulletin" -> "8.30/10.45am", for picker buttons."""
    short = " ".join(re.sub(r"\b(sunday|gathering|bulletin)\b", " ", label, flags=re.IGNORECASE).split())
    return short or label


def file_command_summary(application) -> list[str]:
    """One line per file command, naming the gatherings /bulletin and /outline will ask about."""
    lines = []
    bulletins = bulletin_links(application)
    if bulletins:
        lines.append("/bulletin - " + ", ".join(gathering_label(link.label) for link in bulletins))
    lines += [f"/{link.command} - {link.label}" for link in other_drive_links(application)]
    services: dict[str, OutlineService] = application.bot_data.get(OUTLINE_REGISTRY_KEY, {})
    if len(services) > 1:
        lines.append("/outline - " + ", ".join(service.label or "this week" for service in services.values()))
    return lines


async def _set_bot_commands(application) -> None:
    commands = []
    bulletins = bulletin_links(application)
    if bulletins:
        description = "This week's bulletin (PDF)"
        if len(bulletins) > 1:
            description = f"This week's bulletin, {' or '.join(gathering_label(link.label) for link in bulletins)} (PDF)"
        commands.append(BotCommand("bulletin", description[:256]))
    commands += [
        BotCommand(drive_link.command, f"Download {drive_link.label}"[:256])
        for drive_link in other_drive_links(application)
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
            "Only the maintainer can run /refresh. Files refresh on their own every Sunday at 12am; "
            "if something looks stale, send /report and say which file."
        )
        return

    status_message = await message.reply_text("Refreshing file commands from Linktree...")
    try:
        await refresh_drive_link_commands(context.application)
        listed = file_command_summary(context.application)
        if not listed:
            await status_message.edit_text(
                "Refresh complete, but no Google Drive-backed file links were found."
            )
            return

        command_list = "\n".join(listed)
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

    await _send_drive_link(message, drive_link)


async def bulletin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/bulletin: send this week's bulletin, or ask which gathering's when Linktree lists several."""
    message = _get_message(update)
    if message is None:
        return
    links = bulletin_links(context.application)
    if not links:
        await message.reply_text(
            "I couldn't find a bulletin on Linktree right now. Please try again later, "
            "or send /report if it's Sunday and the bulletin should be up."
        )
        return
    if len(links) == 1:
        await _send_drive_link(message, links[0])
        return
    await message.reply_text(
        "Which gathering's bulletin?",
        reply_markup=_picker(BULLETIN_KIND, [(gathering_label(link.label), link.command) for link in links]),
    )


def _picker(kind: str, choices: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text, callback_data=f"{PICK_PREFIX}|{kind}|{value}")]
        for text, value in choices
    ]
    rows.append([InlineKeyboardButton("All of them", callback_data=f"{PICK_PREFIX}|{kind}|{PICK_ALL}")])
    return InlineKeyboardMarkup(rows)


async def pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A tap on the /bulletin or /outline gathering picker."""
    query = update.callback_query
    if query is None or not query.data:
        return
    await query.answer()
    parts = query.data.split("|", 2)
    if len(parts) != 3 or query.message is None:
        return
    _, kind, value = parts
    message = query.message

    if kind == BULLETIN_KIND:
        links = bulletin_links(context.application)
        chosen = links if value == PICK_ALL else [link for link in links if link.command == value]
        if not chosen:
            await query.edit_message_text("That bulletin isn't on Linktree any more. Send /bulletin to pick again.")
            return
        await query.edit_message_text(f"Bulletin: {', '.join(gathering_label(link.label) for link in chosen)}")
        for link in chosen:
            await _send_drive_link(message, link)
    elif kind in OUTLINE_KINDS:
        try:
            services = await discover_outline_services_async()
        except Exception as exc:
            logger.error("Error listing outline gatherings: %s", exc)
            await query.edit_message_text("An error occurred while fetching the outline. Please try again later.")
            return
        chosen = services if value == PICK_ALL else [service for service in services if service.slug == value]
        if not chosen:
            await query.edit_message_text("That outline isn't in the Drive folder any more. Send /outline to pick again.")
            return
        await query.edit_message_text(
            f"Sermon outline ({OUTLINE_KINDS[kind]}): {', '.join(service.label or 'this week' for service in chosen)}"
        )
        await _send_outlines(message, kind, chosen)


async def _send_drive_link(message, drive_link: DriveLink):
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
    await _outline_command(update, "pdf")


async def outline_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _outline_command(update, "doc")


async def _outline_command(update: Update, kind: str):
    """Send this week's outline, or ask which gathering's when each has its own subfolder."""
    message = _get_message(update)
    if message is None:
        return
    try:
        services = await discover_outline_services_async()
    except Exception as exc:
        logger.error("Error listing outline gatherings: %s", exc)
        await message.reply_text("An error occurred while fetching the outline. Please try again later.")
        return
    if len(services) > 1:
        await message.reply_text(
            f"Which gathering's sermon outline ({OUTLINE_KINDS[kind]})?",
            reply_markup=_picker(kind, [(service.label or "This week", service.slug) for service in services]),
        )
        return
    await _send_outlines(message, kind, services)


async def _send_outlines(message, kind: str, services: list[OutlineService]):
    """Send the outline from each of the given gatherings' folders."""
    kind_label = OUTLINE_KINDS[kind]
    status_message = await message.reply_text(
        f"Fetching the sermon outline ({kind_label})... please wait."
    )
    try:
        missing = []
        for current in services:
            if not await _send_outline(message, current, kind):
                missing.append(current.label or "this week")
        if len(missing) == len(services):
            await status_message.edit_text(
                f"Sorry, I couldn't find the sermon outline ({kind_label})."
            )
        elif missing:
            await status_message.edit_text(
                f"No {kind_label} outline is up yet for: {', '.join(missing)}."
            )
        else:
            await status_message.delete()
    except Exception as exc:
        logger.error("Error sending the %s outline: %s", kind, exc)
        await status_message.edit_text(
            "An error occurred while fetching the outline. Please try again later."
        )


async def _send_outline(message, service: OutlineService, kind: str) -> bool:
    """Send the PDF or Word outline from one gathering's folder; False when the folder has none."""
    if kind == "pdf":
        doc = await resolve_outline_pdf(CACHE, service.folder_url)
    else:
        doc = await resolve_outline_doc(CACHE, service.folder_url)
    if not doc.found:
        return False

    markup = ebook_button(outline_source_id(service.slug))
    if doc.telegram_ref:
        await message.reply_document(document=doc.telegram_ref, caption=service.title, reply_markup=markup)
    elif doc.filepath:
        with open(doc.filepath, "rb") as fh:
            sent = await message.reply_document(
                document=fh, filename=doc.filename, caption=service.title, reply_markup=markup
            )
        if sent.document and doc.drive_file_id:
            CACHE.set_file_id_for_drive_id(doc.drive_file_id, sent.document.file_id)
    return True


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
    """Plain text: the admin answering a forwarded report, or the second half of a user's /report."""
    message = _get_message(update)
    if message is None:
        return
    if is_admin_chat(message.chat_id) and message.reply_to_message is not None:
        if await _answer_report(message, context):
            return
    if not context.user_data.get(AWAITING_REPORT_KEY):
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
        f"Bug report from {who}{handle} (id {user_id}, chat {message.chat_id}, msg {message.message_id}):\n\n{note}",
    )
    if delivered:
        await message.reply_text("Thanks, your report has reached the maintainer.")
    else:
        await message.reply_text("I couldn't deliver your report right now. Please try again later.")


async def _answer_report(message, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Admin replied to a forwarded report: pass the reply on to the reporter. False if it wasn't a report."""
    original = message.reply_to_message
    if original.from_user is None or original.from_user.id != context.bot.id:
        return False
    match = REPORT_HEADER.search(original.text or "")
    if not match:
        return False

    chat_id = int(match.group(1))
    reply_to = (
        ReplyParameters(message_id=int(match.group(2)), allow_sending_without_reply=True)
        if match.group(2) else None
    )
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Reply from the maintainer about your report:\n\n{message.text}",
            reply_parameters=reply_to,
        )
    except Exception as exc:
        logger.warning("Could not deliver report reply to chat %s: %s", chat_id, exc)
        await message.reply_text(f"Couldn't deliver that reply: {exc}")
        return True
    await message.reply_text("Sent to the reporter.")
    return True
