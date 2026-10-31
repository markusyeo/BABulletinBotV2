import asyncio
from types import SimpleNamespace as NS

import pytest
from telegram.error import Conflict

from app import audience, scheduler
from app.services.users import UserStore

ADMIN = 999


class Msg:
    def __init__(self, text="", chat_id=ADMIN):
        self.text, self.chat_id, self.chat = text, chat_id, NS(id=chat_id)
        self.replies = []

    async def reply_text(self, text, reply_markup=None):
        self.replies.append((text, reply_markup))


class Query:
    def __init__(self, data, message):
        self.data, self.message, self.edits = data, message, []

    async def answer(self):
        pass

    async def edit_message_text(self, text, reply_markup=None):
        self.edits.append(text)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_ID", str(ADMIN))
    store = UserStore(str(tmp_path / "users.db"))
    store.import_known([1, 2, 3])
    monkeypatch.setattr(audience, "get_store", lambda: store)
    broadcasts = []

    async def fake_broadcast(context, status, text, recipients):
        broadcasts.append((text, recipients))

    monkeypatch.setattr(audience, "_broadcast", fake_broadcast)
    context = NS(chat_data={}, application=NS(create_task=lambda coro: asyncio.get_event_loop().create_task(coro)))
    return context, broadcasts


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _button(msg, index=0):
    return msg.replies[-1][1].inline_keyboard[0][index].callback_data


def test_announce_needs_button_phrase_and_button(setup):
    context, broadcasts = setup
    start = Msg("/announce Hello church")
    _run(audience.announce(NS(message=start), context))
    _run(audience.announce_callback(NS(callback_query=Query(_button(start), start)), context))
    phrase = Msg(audience.confirmation_phrase(3).upper())  # case and spacing don't matter, wording does
    _run(audience.announce_phrase(NS(message=phrase), context))
    assert broadcasts == []
    _run(audience.announce_callback(NS(callback_query=Query(_button(phrase), phrase)), context))
    _run(asyncio.sleep(0))
    assert broadcasts == [("Hello church", [1, 2, 3])]


def test_wrong_phrase_cancels(setup):
    context, broadcasts = setup
    start = Msg("/announce Hello church")
    _run(audience.announce(NS(message=start), context))
    _run(audience.announce_callback(NS(callback_query=Query(_button(start), start)), context))
    _run(audience.announce_phrase(NS(message=Msg("yes send it")), context))
    assert audience.DRAFT_KEY not in context.chat_data
    # The phrase is no use once the draft is gone, and neither is a stale send button.
    _run(audience.announce_phrase(NS(message=Msg(audience.confirmation_phrase(3))), context))
    stale = f"{audience.ANNOUNCE_PREFIX}|send|{'0' * 8}"
    _run(audience.announce_callback(NS(callback_query=Query(stale, start)), context))
    assert broadcasts == []


def test_send_button_from_preview_cannot_skip_steps(setup):
    context, broadcasts = setup
    start = Msg("/announce Hello church")
    _run(audience.announce(NS(message=start), context))
    draft_id = context.chat_data[audience.DRAFT_KEY]["id"]
    query = Query(f"{audience.ANNOUNCE_PREFIX}|send|{draft_id}", start)
    _run(audience.announce_callback(NS(callback_query=query), context))
    assert broadcasts == [] and "Nothing was sent" in query.edits[-1]


def test_non_admin_cannot_announce(setup):
    context, _ = setup
    msg = Msg("/announce hi", chat_id=5)
    _run(audience.announce(NS(message=msg), context))
    assert msg.replies == [] and context.chat_data == {}


def test_single_conflict_does_not_alert(monkeypatch):
    sent = []

    async def fake_send(bot, text):
        sent.append(text)

    monkeypatch.setattr(scheduler, "send_to_admin", fake_send)
    monkeypatch.setattr(scheduler, "_recent_transient", {})
    monkeypatch.setattr(scheduler, "_last_error_alert", {})
    context = NS(error=Conflict("terminated by other getUpdates request"), bot=None)
    for _ in range(scheduler.TRANSIENT_ALERT_THRESHOLD - 1):
        _run(scheduler.notify_admin_of_error(context))
    assert sent == []
    _run(scheduler.notify_admin_of_error(context))
    assert len(sent) == 1 and "another copy of the bot" in sent[0]
