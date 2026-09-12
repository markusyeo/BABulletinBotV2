"""The admin chat: where refresh summaries, error alerts and user bug reports go."""

import logging
import os

from telegram import Bot

LOGGER = logging.getLogger(__name__)


def admin_chat_id() -> int | None:
    value = os.getenv("ADMIN_CHAT_ID", "").strip()
    return int(value) if value.lstrip("-").isdigit() else None


def is_admin_chat(chat_id: int | None) -> bool:
    admin = admin_chat_id()
    return admin is not None and chat_id == admin


async def send_to_admin(bot: Bot, text: str) -> bool:
    chat_id = admin_chat_id()
    if chat_id is None:
        LOGGER.warning("ADMIN_CHAT_ID is not set; dropping admin message: %s", text[:80])
        return False
    try:
        await bot.send_message(chat_id=chat_id, text=text)
        return True
    except Exception as exc:
        LOGGER.warning("Could not message admin chat %s: %s", chat_id, exc)
        return False
