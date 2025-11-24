import logging
import os
from typing import Callable, Tuple

from telegram import Update
from telegram.ext import ContextTypes

from app.services.downloads import download_songbook
from app.services.drive import (
    download_outline,
    extract_pdf_link_from_google,
    extract_outline_file_id,
    fetch_drive_folder,
)
from app.services.linktree import fetch_linktree, find_bulletin_link, find_songbook_link
from app.services.cache import CACHE

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


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
        f"Use /bulletin to get the latest Sunday Bulletin.\n"
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
    await message.reply_text(
        f"Available commands:\n"
        f"/start - Start the bot\n"
        f"/bulletin - Download the latest Sunday Bulletin\n"
        f"/songbook - Download the latest Songbook\n"
        f"/outline - Download the Sermon Outline (PDF)\n"
        f"/outline_doc - Download the Sermon Outline (DOCX)\n"
        f"/help - Show this help message{linktree_text}"
    )


async def bulletin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _get_message(update)
    if message is None:
        return

    STATUS_MESSAGE_FETCHING = "Fetching the latest bulletin... please wait."
    STATUS_MESSAGE_SENDING = "Sending bulletin link..."
    STATUS_MESSAGE_NOT_FOUND = "Sorry, I couldn't find the 'Sunday Bulletin' link."
    STATUS_MESSAGE_ERROR = "An error occurred while fetching the bulletin. Please try again later."

    status_message = await message.reply_text(STATUS_MESSAGE_FETCHING)

    try:
        html = fetch_linktree()

        link = find_bulletin_link(html)
        if not link:
            await status_message.edit_text(STATUS_MESSAGE_NOT_FOUND)
            return

        direct_link = CACHE.get_direct_link(link)
        if not direct_link:
            logger.info(f"Direct link not in cache, extracting for {link}")
            direct_link = extract_pdf_link_from_google(link)
            if direct_link:
                CACHE.set_direct_link(link, direct_link)
                logger.info(f"Cached direct link: {direct_link}")

        if direct_link:
            await status_message.edit_text(STATUS_MESSAGE_SENDING)
            try:
                await message.reply_document(document=direct_link)
                await status_message.delete()
                return
            except Exception as e:
                logger.error(f"Failed to send direct link: {e}")
                await status_message.edit_text(STATUS_MESSAGE_ERROR)

    except Exception as e:
        logger.error(f"Error in bulletin_new command: {e}")
        await status_message.edit_text(STATUS_MESSAGE_ERROR)


async def songbook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _get_message(update)
    if message is None:
        return

    STATUS_MESSAGE_FETCHING = "Fetching the latest songbook..."
    STATUS_MESSAGE_SENDING = "Sending songbook..."
    STATUS_MESSAGE_NOT_FOUND = "Sorry, I couldn't find the 'Songbook' link."
    STATUS_MESSAGE_ERROR = "An error occurred while fetching the songbook. Please try again later."

    status_message = await message.reply_text(STATUS_MESSAGE_FETCHING)

    try:
        html = fetch_linktree()

        link = find_songbook_link(html)
        if not link:
            await status_message.edit_text(STATUS_MESSAGE_NOT_FOUND)
            return

        cached_file_id = CACHE.get_file_id_for_url(link)
        if cached_file_id:
            await status_message.edit_text(STATUS_MESSAGE_SENDING)
            await message.reply_document(document=cached_file_id)
            await status_message.delete()
            return

        filepath, filename = download_songbook(link)

        await status_message.edit_text(STATUS_MESSAGE_SENDING)
        with open(filepath, "rb") as file_handle:
            sent_message = await message.reply_document(
                document=file_handle,
                filename=filename,
            )

        if sent_message.document:
            CACHE.set_file_id_for_name(filename, sent_message.document.file_id)
            CACHE.set_file_id_for_url(link, sent_message.document.file_id)

        await status_message.delete()

    except Exception as exc:
        logger.error(f"Error in songbook command: {exc}")
        await status_message.edit_text(STATUS_MESSAGE_ERROR)


async def outline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _get_message(update)
    if message is None:
        return

    STATUS_MESSAGE_FETCHING = "Fetching the sermon outline (PDF)... please wait."
    STATUS_MESSAGE_SENDING = "Sending outline link..."
    STATUS_MESSAGE_NOT_FOUND = "Sorry, I couldn't find the PDF outline."
    STATUS_MESSAGE_ERROR = "An error occurred while fetching the outline. Please try again later."

    status_message = await message.reply_text(STATUS_MESSAGE_FETCHING)

    try:
        html = fetch_drive_folder()

        file_id = extract_outline_file_id(html, "application/pdf")
        if not file_id:
            await status_message.edit_text(STATUS_MESSAGE_NOT_FOUND)
            return

        view_url = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
        direct_link = CACHE.get_direct_link(view_url)
        if not direct_link:
            logger.info(
                "Outline direct link not cached, extracting for %s", view_url)
            direct_link = extract_pdf_link_from_google(view_url)
            if direct_link:
                CACHE.set_direct_link(view_url, direct_link)

        if direct_link:
            await status_message.edit_text(STATUS_MESSAGE_SENDING)
            try:
                await message.reply_document(document=direct_link)
                await status_message.delete()
                return
            except Exception as exc:
                logger.error("Failed to send outline link: %s", exc)
                await status_message.edit_text(STATUS_MESSAGE_ERROR)

    except Exception as e:
        logger.error(f"Error in outline command: {e}")
        await status_message.edit_text(STATUS_MESSAGE_ERROR)


async def outline_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _get_message(update)
    if message is None:
        return

    STATUS_MESSAGE_FETCHING = "Fetching the sermon outline (DOC)... please wait."
    STATUS_MESSAGE_SENDING = "Sending outline..."
    STATUS_MEESSAGE_NOT_FOUND_ERROR = "Sorry, I could not find the outline(docx)."
    STATUS_MESSAGE_ERROR = "An error occurred while fetching the outline. Please try again later."

    status_message = await message.reply_text(STATUS_MESSAGE_FETCHING)

    try:
        html = fetch_drive_folder()

        file_id = extract_outline_file_id(html, "wordprocessingml")
        if not file_id:
            # Try msword just in case
            file_id = extract_outline_file_id(html, "msword")

        if not file_id:
            await status_message.edit_text(STATUS_MEESSAGE_NOT_FOUND_ERROR)
            return

        cached_drive_file_id = CACHE.get_file_id_for_drive_id(file_id)
        if cached_drive_file_id:
            logger.info("Using cached file_id for Drive id %s", file_id)
            await status_message.edit_text(STATUS_MESSAGE_SENDING)
            await message.reply_document(document=cached_drive_file_id)
            await status_message.delete()
            return

        filepath, filename = download_outline(
            file_id, filename_prefix="outline_doc")

        await status_message.edit_text(STATUS_MESSAGE_SENDING)
        with open(filepath, 'rb') as file_handle:
            sent_message = await message.reply_document(document=file_handle, filename=filename)

        if sent_message.document:
            CACHE.set_file_id_for_name(
                filename, sent_message.document.file_id)
            CACHE.set_file_id_for_drive_id(
                file_id, sent_message.document.file_id)

        await status_message.delete()

    except Exception as e:
        logger.error(f"Error in outline_doc command: {e}")
        await status_message.edit_text(STATUS_MESSAGE_ERROR)
