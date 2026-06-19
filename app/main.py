from app.bot import (
    start,
    help_command,
    songbook,
    outline,
    outline_doc,
    refresh,
    refresh_drive_link_commands,
    set_bot_commands,
)
from telegram.ext import ApplicationBuilder, CommandHandler
from dotenv import load_dotenv
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables.")
        return

    application = ApplicationBuilder().token(token).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("refresh", refresh))
    application.add_handler(CommandHandler("songbook", songbook))
    application.add_handler(CommandHandler("outline", outline))
    application.add_handler(CommandHandler("outline_doc", outline_doc))

    application.run_polling()


async def post_init(application):
    """Sets the bot commands for autosuggestion."""
    try:
        await refresh_drive_link_commands(application)
    except Exception as exc:
        logger.error("Failed to refresh file commands during startup: %s", exc)
        await set_bot_commands(application)


if __name__ == '__main__':
    main()
