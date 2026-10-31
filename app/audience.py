"""Knowing who uses the bot and reaching them: user tracking, /stats and /announce (admin only)."""

import asyncio
import logging
import secrets
import time

from telegram import Chat, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Forbidden, RetryAfter
from telegram.ext import ContextTypes

from app.admin import is_admin_chat
from app.services.users import get_store

LOGGER = logging.getLogger(__name__)

ANNOUNCE_PREFIX = "an"
ANNOUNCE_PATTERN = rf"^{ANNOUNCE_PREFIX}\|"
DRAFT_KEY = "announce_draft"
# Telegram allows about 30 messages a second to different chats; stay well under it.
SEND_INTERVAL_SECONDS = 0.1


async def track_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs before every other handler: note who sent the update and which command it was."""
    user = update.effective_user
    if user is None or user.is_bot:
        return
    chat = update.effective_chat
    command = None
    message = update.message
    if message is not None and message.text and message.text.startswith("/"):
        command = message.text.split()[0].split("@")[0].lstrip("/").lower()[:32] or None
    try:
        get_store().record(
            user.id,
            user.full_name,
            user.username,
            private=chat is not None and chat.type == Chat.PRIVATE,
            command=command,
        )
    except Exception as exc:
        LOGGER.warning("Could not record user %s: %s", user.id, exc)


def import_known_users(application) -> None:
    """Carry over users from the per-user settings file, which predates the user table."""
    added = get_store().import_known(application.user_data.keys())
    if added:
        LOGGER.info("Imported %d users from the per-user settings file", added)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message is None or not is_admin_chat(message.chat_id):
        return
    data = get_store().stats()
    lines = [
        f"Users: {data['total']} in total, {data['reachable']} reachable by /announce.",
        f"Active: {data['active_1d']} in the last day, {data['active_7d']} in 7 days, "
        f"{data['active_30d']} in 30 days.",
        f"New in the last 7 days: {data['new_7d']}.",
    ]
    if data["never_seen"]:
        lines.append(f"{data['never_seen']} came from before tracking started and haven't been back since.")
    if data["blocked"]:
        lines.append(f"{data['blocked']} blocked the bot or deleted their account.")
    if data["top_commands_7d"]:
        lines += ["", "Commands, last 7 days:"]
        lines += [f"/{command}: {count}" for command, count in data["top_commands_7d"]]
    await message.reply_text("\n".join(lines))


# Sending to everyone can't be undone, so /announce takes three separate confirmations:
# a button under the preview, a typed phrase that names the audience size, and a last button.
DRAFT_TTL_SECONDS = 10 * 60
STAGE_PREVIEW, STAGE_PHRASE, STAGE_FINAL = "preview", "phrase", "final"


def confirmation_phrase(count: int) -> str:
    return f"I have read this announcement and want to send it to {count} users"


def _normalise(text: str) -> str:
    return " ".join(text.split()).lower()


def _current_draft(context: ContextTypes.DEFAULT_TYPE, stage: str, draft_id: str | None = None) -> dict | None:
    """The pending draft if it is at this stage, still fresh and (for buttons) the one the button belongs to."""
    draft = context.chat_data.get(DRAFT_KEY)
    if not draft or draft["stage"] != stage:
        return None
    if time.monotonic() - draft["created"] > DRAFT_TTL_SECONDS:
        context.chat_data.pop(DRAFT_KEY, None)
        return None
    if draft_id is not None and draft["id"] != draft_id:
        return None
    return draft


def _buttons(draft_id: str, go_label: str, go_step: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(go_label, callback_data=f"{ANNOUNCE_PREFIX}|{go_step}|{draft_id}"),
        InlineKeyboardButton("Cancel", callback_data=f"{ANNOUNCE_PREFIX}|x|{draft_id}"),
    ]])


async def announce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/announce <message>, step 1 of 3: show exactly what will be sent and to how many people."""
    message = update.message
    if message is None or not is_admin_chat(message.chat_id):
        return
    parts = (message.text or "").split(maxsplit=1)
    text = parts[1].strip() if len(parts) > 1 else ""
    if not text:
        await message.reply_text(
            "Write the announcement after the command, for example:\n"
            "/announce Bulletins are late this week, they'll be up by 10am."
        )
        return
    recipients = get_store().recipients()
    if not recipients:
        await message.reply_text("Nobody can receive announcements yet.")
        return
    draft_id = secrets.token_hex(4)
    # The recipient list is fixed now, so the number typed in step 2 is the number that gets the message.
    context.chat_data[DRAFT_KEY] = {
        "id": draft_id, "text": text, "recipients": recipients,
        "stage": STAGE_PREVIEW, "created": time.monotonic(),
    }
    await message.reply_text(
        f"Step 1 of 3. Read it carefully: this exact text goes to {len(recipients)} users.\n"
        f"──────────\n{text}\n──────────",
        reply_markup=_buttons(draft_id, "Text is right", "ok"),
    )


async def announce_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or query.message is None or not is_admin_chat(query.message.chat.id):
        return
    await query.answer()
    parts = (query.data or "").split("|")
    step, draft_id = (parts[1], parts[2]) if len(parts) == 3 else ("x", "")

    if step == "ok":
        draft = _current_draft(context, STAGE_PREVIEW, draft_id)
        if draft is None:
            await query.edit_message_text("This draft is no longer pending. Start again with /announce.")
            return
        draft["stage"] = STAGE_PHRASE
        await query.edit_message_text(
            f"Step 2 of 3. To continue, send this sentence exactly:\n\n"
            f"{confirmation_phrase(len(draft['recipients']))}\n\n"
            "Anything else cancels the announcement. Expires 10 minutes after you started."
        )
        return

    if step == "send":
        draft = _current_draft(context, STAGE_FINAL, draft_id)
        if draft is None:
            await query.edit_message_text("This draft is no longer pending. Nothing was sent.")
            return
        context.chat_data.pop(DRAFT_KEY, None)
        await query.edit_message_text(f"Sending to {len(draft['recipients'])} users:\n\n{draft['text']}")
        # Sending can take a while; don't hold up everyone else's commands meanwhile.
        context.application.create_task(_broadcast(context, query.message, draft["text"], draft["recipients"]))
        return

    draft = context.chat_data.get(DRAFT_KEY)
    if draft and draft["id"] == draft_id:
        context.chat_data.pop(DRAFT_KEY, None)
    await query.edit_message_text("Announcement cancelled. Nothing was sent.")


async def announce_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 2 of 3: the admin types the confirmation sentence. A wrong sentence cancels the draft."""
    message = update.message
    if message is None or not message.text or not is_admin_chat(message.chat_id):
        return
    draft = _current_draft(context, STAGE_PHRASE)
    if draft is None:
        if context.chat_data.get(DRAFT_KEY, {}).get("stage") == STAGE_PHRASE:
            await message.reply_text("That draft expired. Nothing was sent. Start again with /announce.")
        return
    count = len(draft["recipients"])
    if _normalise(message.text) != _normalise(confirmation_phrase(count)):
        context.chat_data.pop(DRAFT_KEY, None)
        await message.reply_text("That didn't match, so the announcement is cancelled. Nothing was sent.")
        return
    draft["stage"] = STAGE_FINAL
    await message.reply_text(
        f"Step 3 of 3. Last chance: once you tap Send, {count} people get this and it can't be taken back.\n"
        f"──────────\n{draft['text']}\n──────────",
        reply_markup=_buttons(draft["id"], f"Send to {count} users now", "send"),
    )


async def _broadcast(context: ContextTypes.DEFAULT_TYPE, status_message, text: str, recipients: list[int]) -> None:
    store = get_store()
    sent = gone = failed = 0
    for user_id in recipients:
        try:
            await _send_with_retry(context, user_id, text)
            sent += 1
        except Forbidden:
            store.mark_blocked(user_id)
            gone += 1
        except Exception as exc:
            if "chat not found" in str(exc).lower():
                store.mark_blocked(user_id)
                gone += 1
            else:
                LOGGER.warning("Announcement to %s failed: %s", user_id, exc)
                failed += 1
        await asyncio.sleep(SEND_INTERVAL_SECONDS)

    summary = f"Announcement sent to {sent} users."
    if gone:
        summary += f" {gone} have blocked the bot or deleted their account; they're skipped from now on."
    if failed:
        summary += f" {failed} failed for other reasons (see the logs)."
    await status_message.reply_text(summary)


async def _send_with_retry(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str) -> None:
    try:
        await context.bot.send_message(chat_id=chat_id, text=text)
    except RetryAfter as exc:
        delay = exc.retry_after.total_seconds() if hasattr(exc.retry_after, "total_seconds") else exc.retry_after
        await asyncio.sleep(float(delay) + 1)
        await context.bot.send_message(chat_id=chat_id, text=text)
