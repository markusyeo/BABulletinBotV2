"""Scheduled Linktree refresh and admin notifications."""

import logging
import os
import time as clock
from datetime import time
from zoneinfo import ZoneInfo

from telegram.ext import Application, ContextTypes

from app.admin import send_to_admin
from app.bot import file_command_summary, refresh_drive_link_commands

LOGGER = logging.getLogger(__name__)

JOB_NAME = "auto_refresh"
RETRY_DELAY_SECONDS = 600
MAX_RETRIES = 3
ERROR_ALERT_COOLDOWN_SECONDS = 600
# A dropped connection to Telegram makes the bot's own next poll "conflict" with the one Telegram still
# holds open, and timeouts come in bursts. Only a run of these means something is really wrong (a second
# bot polling the same token conflicts every few seconds), so they alert after several in a few minutes.
TRANSIENT_ERRORS = {"Conflict", "TimedOut", "NetworkError"}
TRANSIENT_ALERT_THRESHOLD = 5
TRANSIENT_WINDOW_SECONDS = 300
_last_error_alert: dict[str, float] = {}
_recent_transient: dict[str, list[float]] = {}


def schedule_auto_refresh(application: Application) -> None:
    timezone = ZoneInfo(os.getenv("TIMEZONE", "Asia/Singapore"))
    hour, minute = _parse_time(os.getenv("AUTO_REFRESH_TIME", "00:00"))
    application.job_queue.run_daily(
        auto_refresh,
        time=time(hour, minute, tzinfo=timezone),
        days=(0,),  # PTB: 0=Sunday, so 00:00 Sunday == Saturday night/Sunday 12am
        name=JOB_NAME,
        data={"attempt": 0},
    )
    LOGGER.info("Auto-refresh scheduled weekly (Sat night/Sun 00:00) at %02d:%02d %s", hour, minute, timezone.key)


async def auto_refresh(context: ContextTypes.DEFAULT_TYPE) -> None:
    attempt = (context.job.data or {}).get("attempt", 0)
    try:
        await refresh_drive_link_commands(context.application)
    except Exception as exc:
        LOGGER.error("Auto-refresh attempt %d failed: %s", attempt + 1, exc)
        if attempt + 1 < MAX_RETRIES:
            context.job_queue.run_once(auto_refresh, RETRY_DELAY_SECONDS, data={"attempt": attempt + 1}, name=f"{JOB_NAME}_retry")
        else:
            await send_to_admin(context.bot, "Auto-refresh failed three times. Run /refresh manually.")
        return

    summary = "\n".join(file_command_summary(context.application)) or "no Drive-backed links found"
    LOGGER.info("Auto-refresh complete: %s", summary.replace("\n", "; "))
    await send_to_admin(context.bot, f"Auto-refresh complete:\n{summary}")


async def notify_admin_of_error(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tell the admin chat about an unhandled error, at most once per error type every ten minutes."""
    error = context.error
    if error is None:
        return
    key = type(error).__name__
    now = clock.monotonic()
    note = ""
    if key in TRANSIENT_ERRORS:
        recent = [t for t in _recent_transient.get(key, []) if now - t < TRANSIENT_WINDOW_SECONDS] + [now]
        _recent_transient[key] = recent
        if len(recent) < TRANSIENT_ALERT_THRESHOLD:
            LOGGER.info("%s %d/%d in %ds; not alerting yet", key, len(recent), TRANSIENT_ALERT_THRESHOLD, TRANSIENT_WINDOW_SECONDS)
            return
        note = f"\n{len(recent)} times in the last {TRANSIENT_WINDOW_SECONDS // 60} minutes."
        if key == "Conflict":
            note += " That many usually means another copy of the bot is running with this token."
    if now - _last_error_alert.get(key, 0) < ERROR_ALERT_COOLDOWN_SECONDS:
        return
    _last_error_alert[key] = now
    detail = str(error)[:300]
    await send_to_admin(context.bot, f"Bot error: {key}\n{detail}{note}\nCheck `docker logs babulletinbot` for the traceback.")


def _parse_time(value: str) -> tuple[int, int]:
    try:
        hour, minute = value.strip().split(":")
        return int(hour) % 24, int(minute) % 60
    except ValueError:
        LOGGER.warning("AUTO_REFRESH_TIME '%s' is not HH:MM; using 00:00", value)
        return 0, 0
