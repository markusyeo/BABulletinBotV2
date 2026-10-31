import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
    PersistenceInput,
    PicklePersistence,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from telegram import Update  # noqa: E402

from app.audience import (  # noqa: E402
    ANNOUNCE_PATTERN,
    announce,
    announce_callback,
    announce_phrase,
    import_known_users,
    stats,
    track_user,
)
from app.bot import (  # noqa: E402
    PICK_PATTERN,
    bulletin,
    capture_report,
    help_command,
    report,
    outline,
    outline_doc,
    pick_callback,
    refresh,
    refresh_drive_link_commands,
    set_bot_commands,
    songbook,
    start,
)
from app.ebook_flow import CALLBACK_PATTERN, ebook_callback, ebook_command  # noqa: E402
from app.scheduler import notify_admin_of_error, schedule_auto_refresh  # noqa: E402
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
    # Only user_data is persisted: it holds each user's remembered e-reader.
    # bot_data carries live handler objects and must stay in memory.
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

    # Group -1 runs before the command handlers and never stops them.
    application.add_handler(TypeHandler(Update, track_user), group=-1)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("refresh", refresh))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("announce", announce))
    application.add_handler(CommandHandler("bulletin", bulletin))
    application.add_handler(CommandHandler("songbook", songbook))
    application.add_handler(CommandHandler("outline", outline))
    application.add_handler(CommandHandler("outline_doc", outline_doc))
    application.add_handler(CommandHandler("ebook", ebook_command))
    application.add_handler(CommandHandler("report", report))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, capture_report))
    # Its own group, so the admin's typed /announce confirmation never swallows a report reply.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, announce_phrase), group=1)
    application.add_handler(CallbackQueryHandler(ebook_callback, pattern=CALLBACK_PATTERN))
    application.add_handler(CallbackQueryHandler(pick_callback, pattern=PICK_PATTERN))
    application.add_handler(CallbackQueryHandler(announce_callback, pattern=ANNOUNCE_PATTERN))
    application.add_error_handler(log_error)

    schedule_auto_refresh(application)
    application.run_polling()


async def post_init(application):
    """Build the Drive-backed commands and publish the command list to Telegram."""
    try:
        import_known_users(application)
    except Exception as exc:
        logger.error("Failed to import known users: %s", exc)
    try:
        await refresh_drive_link_commands(application)
    except Exception as exc:
        logger.error("Failed to refresh file commands during startup: %s", exc)
        await set_bot_commands(application)


async def log_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled error while processing %s", update, exc_info=context.error)
    await notify_admin_of_error(context)


if __name__ == '__main__':
    main()
