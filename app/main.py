import logging
import os
import sys
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler
from bot import start, help_command, bulletin

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables.")
        sys.exit(1)

    # Configure request with higher timeouts for file uploads
    application = (
        ApplicationBuilder()
        .token(token)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .pool_timeout(30)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("bulletin", bulletin))

    logger.info("Bot is starting...")
    application.run_polling()

async def post_init(application):
    """Sets the bot commands for autosuggestion."""
    from telegram import BotCommand
    commands = [
        BotCommand("bulletin", "Download the latest Sunday Bulletin"),
        BotCommand("help", "Show available commands"),
        BotCommand("start", "Start the bot"),
    ]
    await application.bot.set_my_commands(commands)


if __name__ == '__main__':
    main()
