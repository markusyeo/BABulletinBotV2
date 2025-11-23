import logging
import os
from telegram import Update
from telegram.ext import ContextTypes
from bulletin import fetch_linktree, find_bulletin_link, download_bulletin

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message."""
    await update.message.reply_text(
        "Welcome to BABulletinBot_v2! \n"
        "Use /bulletin to get the latest Sunday Bulletin.\n"
        "Use /help to see available commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a help message."""
    await update.message.reply_text(
        "Available commands:\n"
        "/bulletin - Download the latest Sunday Bulletin\n"
        "/help - Show this help message"
    )

# Simple in-memory cache for file_ids: {checksum_or_filename: file_id}
# In a real production app, this should be persistent (DB or file).
FILE_ID_CACHE = {}

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
