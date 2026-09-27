import asyncio
from types import SimpleNamespace

from app import bot

BOT_ID = 42


class FakeBot:
    id = BOT_ID

    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    async def send_message(self, **kwargs):
        if self.fail:
            raise RuntimeError("Forbidden: bot was blocked by the user")
        self.sent.append(kwargs)


class FakeMessage:
    def __init__(self, text, reply_to=None, chat_id=1):
        self.text = text
        self.reply_to_message = reply_to
        self.chat_id = chat_id
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


def _report(text, from_id=BOT_ID):
    return SimpleNamespace(text=text, from_user=SimpleNamespace(id=from_id))


def _answer(original, fake_bot):
    message = FakeMessage("Fixed now, thanks!", reply_to=original)
    handled = asyncio.run(bot._answer_report(message, SimpleNamespace(bot=fake_bot)))
    return handled, message


def test_reply_to_new_report_threads_under_original():
    fake_bot = FakeBot()
    original = _report("Bug report from Ann Lee @ann (id 7, chat 555, msg 99):\n\n/outline is broken")
    handled, message = _answer(original, fake_bot)
    assert handled and message.replies == ["Sent to the reporter."]
    [sent] = fake_bot.sent
    assert sent["chat_id"] == 555 and sent["reply_parameters"].message_id == 99
    assert sent["text"].endswith("Fixed now, thanks!")


def test_reply_to_report_sent_before_msg_ids():
    fake_bot = FakeBot()
    handled, _ = _answer(_report("Bug report from Ann (id 7, chat -100123):\n\nhello"), fake_bot)
    assert handled and fake_bot.sent[0]["chat_id"] == -100123
    assert fake_bot.sent[0]["reply_parameters"] is None


def test_ignores_replies_to_other_messages():
    fake_bot = FakeBot()
    assert not _answer(_report("Auto-refresh complete: /bulletin_2pm"), fake_bot)[0]
    assert not _answer(_report("Bug report from X (id 1, chat 2):", from_id=9), fake_bot)[0]
    assert fake_bot.sent == []


def test_tells_admin_when_delivery_fails():
    handled, message = _answer(_report("Bug report from Ann (id 7, chat 555, msg 9):\n\nx"), FakeBot(fail=True))
    assert handled and message.replies[0].startswith("Couldn't deliver that reply")
