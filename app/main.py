import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    PersistenceInput,
    PicklePersistence,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bot import (  # noqa: E402
    help_command,
    outline,
    outline_doc,
    refresh,
    refresh_drive_link_commands,
    set_bot_commands,
    songbook,
    start,
)
from app.scheduler import schedule_auto_refresh  # noqa: E402
from app.utils.common import CACHE_DIR, ensure_dir  # noqa: E402

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables.")
        return

    ensure_dir(CACHE_DIR)
    # Only user_data is persisted; bot_data carries live handler objects and must stay in memory.
    persistence = PicklePersistence(
        filepath=os.path.join(CACHE_DIR, "bot_state.pickle"),
        store_data=PersistenceInput(bot_data=False, chat_data=False, user_data=True, callback_data=False),
    )
    application = (
        ApplicationBuilder()
        .token(token)
        .persistence(persistence)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("refresh", refresh))
    application.add_handler(CommandHandler("songbook", songbook))
    application.add_handler(CommandHandler("outline", outline))
    application.add_handler(CommandHandler("outline_doc", outline_doc))
    application.add_error_handler(log_error)

    schedule_auto_refresh(application)
    application.run_polling()


async def post_init(application):
    """Build the Drive-backed commands and publish the command list to Telegram."""
    try:
        await refresh_drive_link_commands(application)
    except Exception as exc:
        logger.error("Failed to refresh file commands during startup: %s", exc)
        await set_bot_commands(application)


async def log_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled error while processing %s", update, exc_info=context.error)


if __name__ == '__main__':
    main()
