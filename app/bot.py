import logging
import os
from telegram import Update
from telegram.ext import ContextTypes
from bulletin import (
    fetch_linktree,
    find_bulletin_link,
    download_bulletin,
    find_songbook_link,
    download_songbook,
    LINKTREE_URL,
    fetch_drive_folder,
    extract_outline_file_id,
    download_outline
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Simple in-memory cache for file_ids: {checksum_or_filename: file_id}
# In a real production app, this should be persistent (DB or file).
FILE_ID_CACHE = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Hi! I'm the Bukit Arang Bulletin Bot.\n"
        f"Use /bulletin to get the latest Sunday Bulletin.\n"
        f"Use /songbook to get the latest Songbook.\n"
        f"Use /outline for the Sermon Outline (PDF).\n"
        f"Use /outline_doc for the Sermon Outline (DOCX).\n"
        f"Visit our Linktree: {LINKTREE_URL}"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Available commands:\n"
        f"/start - Start the bot\n"
        f"/bulletin - Download the latest Sunday Bulletin\n"
        f"/songbook - Download the latest Songbook\n"
        f"/outline - Download the Sermon Outline (PDF)\n"
        f"/outline_doc - Download the Sermon Outline (DOCX)\n"
        f"/help - Show this help message\n"
        f"Linktree: {LINKTREE_URL}"
    )

async def bulletin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetches and sends the bulletin PDF."""
    status_message = await update.message.reply_text("Fetching the latest bulletin... please wait.")

    try:
        # 1. Fetch Linktree
        html = fetch_linktree()

        # 2. Find Link
        link = find_bulletin_link(html)
        if not link:
            await status_message.edit_text("Sorry, I couldn't find the 'Sunday Bulletin' link.")
            return

        # 3. Download (or get from cache)
        # Now returns (filepath, filename)
        filepath, filename = download_bulletin(link)

        # 4. Send File
        # Check if we have a cached file_id for this filename
        if filename in FILE_ID_CACHE:
            logger.info(f"Using cached file_id for {filename}")
            await status_message.edit_text("Sending bulletin...")
            await update.message.reply_document(document=FILE_ID_CACHE[filename])
        else:
            logger.info(f"Uploading new file: {filename}")
            await status_message.edit_text("Uploading bulletin...")
            message = await update.message.reply_document(document=open(filepath, 'rb'), filename=filename)

            # Cache the file_id
            if message.document:
                FILE_ID_CACHE[filename] = message.document.file_id
                logger.info(f"Cached file_id for {filename}: {message.document.file_id}")

        await status_message.delete()

    except Exception as e:
        logger.error(f"Error in bulletin command: {e}")
        await status_message.edit_text("An error occurred while fetching the bulletin. Please try again later.")

async def songbook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetches and sends the songbook PDF."""
    status_message = await update.message.reply_text("Fetching the latest songbook... please wait.")

    try:
        # 1. Fetch Linktree
        html = fetch_linktree()

        # 2. Find Link
        link = find_songbook_link(html)
        if not link:
            await status_message.edit_text("Sorry, I couldn't find the 'Songbook' link.")
            return

        # 3. Download (or get from cache)
        # Now returns (filepath, filename)
        filepath, filename = download_songbook(link)

        # 4. Send File
        # Check if we have a cached file_id for this filename
        if filename in FILE_ID_CACHE:
            logger.info(f"Using cached file_id for {filename}")
            await status_message.edit_text("Sending songbook...")
            await update.message.reply_document(document=FILE_ID_CACHE[filename])
        else:
            logger.info(f"Uploading new file: {filename}")
            await status_message.edit_text("Uploading songbook...")
            message = await update.message.reply_document(document=open(filepath, 'rb'), filename=filename)

            # Cache the file_id
            if message.document:
                FILE_ID_CACHE[filename] = message.document.file_id
                logger.info(f"Cached file_id for {filename}: {message.document.file_id}")

        await status_message.delete()

    except Exception as e:
        logger.error(f"Error in songbook command: {e}")
        await status_message.edit_text("An error occurred while fetching the songbook. Please try again later.")

async def outline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_message = await update.message.reply_text("Fetching the sermon outline (PDF)... please wait.")

    try:
        # 1. Fetch Drive Folder
        html = fetch_drive_folder()

        # 2. Find PDF ID
        file_id = extract_outline_file_id(html, "application/pdf")
        if not file_id:
            await status_message.edit_text("Sorry, I couldn't find the PDF outline.")
            return

        # 3. Download
        filepath, filename = download_outline(file_id, filename_prefix="outline_pdf")

        # 4. Send File
        if filename in FILE_ID_CACHE:
            logger.info(f"Using cached file_id for {filename}")
            await status_message.edit_text("Sending outline...")
            await update.message.reply_document(document=FILE_ID_CACHE[filename])
        else:
            logger.info(f"Uploading new file: {filename}")
            await status_message.edit_text("Uploading outline...")
            message = await update.message.reply_document(document=open(filepath, 'rb'), filename=filename)

            if message.document:
                FILE_ID_CACHE[filename] = message.document.file_id

        await status_message.delete()

    except Exception as e:
        logger.error(f"Error in outline command: {e}")
        await status_message.edit_text("An error occurred while fetching the outline. Please try again later.")

async def outline_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_message = await update.message.reply_text("Fetching the sermon outline (DOCX)... please wait.")

    try:
        # 1. Fetch Drive Folder
        html = fetch_drive_folder()

        # 2. Find DOC ID (look for wordprocessingml or msword)
        file_id = extract_outline_file_id(html, "wordprocessingml")
        if not file_id:
            # Try msword just in case
            file_id = extract_outline_file_id(html, "msword")

        if not file_id:
            await status_message.edit_text("Sorry, I couldn't find the DOCX outline.")
            return

        # 3. Download
        filepath, filename = download_outline(file_id, filename_prefix="outline_doc")

        # 4. Send File
        if filename in FILE_ID_CACHE:
            logger.info(f"Using cached file_id for {filename}")
            await status_message.edit_text("Sending outline...")
            await update.message.reply_document(document=FILE_ID_CACHE[filename])
        else:
            logger.info(f"Uploading new file: {filename}")
            await status_message.edit_text("Uploading outline...")
            message = await update.message.reply_document(document=open(filepath, 'rb'), filename=filename)

            if message.document:
                FILE_ID_CACHE[filename] = message.document.file_id

        await status_message.delete()

    except Exception as e:
        logger.error(f"Error in outline_doc command: {e}")
        await status_message.edit_text("An error occurred while fetching the outline. Please try again later.")