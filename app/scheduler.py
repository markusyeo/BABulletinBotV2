"""Scheduled Linktree refresh and admin notifications."""

import logging
import os
import time as clock
from datetime import time
from zoneinfo import ZoneInfo

from telegram.ext import Application, ContextTypes

from app.bot import refresh_drive_link_commands

LOGGER = logging.getLogger(__name__)

JOB_NAME = "auto_refresh"
RETRY_DELAY_SECONDS = 600
MAX_RETRIES = 3
ERROR_ALERT_COOLDOWN_SECONDS = 600
_last_error_alert: dict[str, float] = {}


def schedule_auto_refresh(application: Application) -> None:
    timezone = ZoneInfo(os.getenv("TIMEZONE", "Asia/Singapore"))
    hour, minute = _parse_time(os.getenv("AUTO_REFRESH_TIME", "00:00"))
    application.job_queue.run_daily(
        auto_refresh,
        time=time(hour, minute, tzinfo=timezone),
        name=JOB_NAME,
        data={"attempt": 0},
    )
    LOGGER.info("Auto-refresh scheduled daily at %02d:%02d %s", hour, minute, timezone.key)


async def auto_refresh(context: ContextTypes.DEFAULT_TYPE) -> None:
    attempt = (context.job.data or {}).get("attempt", 0)
    try:
        links = await refresh_drive_link_commands(context.application)
    except Exception as exc:
        LOGGER.error("Auto-refresh attempt %d failed: %s", attempt + 1, exc)
        if attempt + 1 < MAX_RETRIES:
            context.job_queue.run_once(auto_refresh, RETRY_DELAY_SECONDS, data={"attempt": attempt + 1}, name=f"{JOB_NAME}_retry")
        else:
            await _notify_admin(context, "Auto-refresh failed three times. Run /refresh manually.")
        return

    summary = ", ".join(f"/{link.command}" for link in links) or "no Drive-backed links found"
    LOGGER.info("Auto-refresh complete: %s", summary)
    await _notify_admin(context, f"Auto-refresh complete: {summary}")


async def notify_admin_of_error(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tell the admin chat about an unhandled error, at most once per error type every ten minutes."""
    error = context.error
    if error is None:
        return
    key = type(error).__name__
    now = clock.monotonic()
    if now - _last_error_alert.get(key, 0) < ERROR_ALERT_COOLDOWN_SECONDS:
        return
    _last_error_alert[key] = now
    detail = str(error)[:300]
    await _notify_admin(context, f"Bot error: {key}\n{detail}\nCheck `docker logs babulletinbot` for the traceback.")


async def _notify_admin(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    chat_id = os.getenv("ADMIN_CHAT_ID")
    if not chat_id:
        return
    try:
        await context.bot.send_message(chat_id=int(chat_id), text=text)
    except Exception as exc:
        LOGGER.warning("Could not notify admin chat %s: %s", chat_id, exc)


def _parse_time(value: str) -> tuple[int, int]:
    try:
        hour, minute = value.strip().split(":")
        return int(hour) % 24, int(minute) % 60
    except ValueError:
        LOGGER.warning("AUTO_REFRESH_TIME '%s' is not HH:MM; using 00:00", value)
        return 0, 0
