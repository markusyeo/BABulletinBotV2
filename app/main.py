from app.bot import start, help_command, bulletin, songbook, outline, outline_doc
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
    application.add_handler(CommandHandler("bulletin", bulletin))
    application.add_handler(CommandHandler("songbook", songbook))
    application.add_handler(CommandHandler("outline", outline))
    application.add_handler(CommandHandler("outline_doc", outline_doc))

    application.run_polling()


async def post_init(application):
    """Sets the bot commands for autosuggestion."""
    from telegram import BotCommand
    commands = [
        BotCommand("bulletin", "Download the latest Sunday Bulletin"),
        BotCommand("songbook", "Download the latest Songbook"),
        BotCommand("outline", "Download the Sermon Outline (PDF)"),
        BotCommand("outline_doc", "Download the Sermon Outline (DOCX)"),
        BotCommand("help", "Show available commands"),
        BotCommand("start", "Start the bot"),
    ]
    await application.bot.set_my_commands(commands)


if __name__ == '__main__':
    main()
