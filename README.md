# BABulletinBot v2

A Telegram bot for Bukit Arang Church. It reads the church Linktree and Google Drive folder, hands out the week's Sunday bulletin, the songbook and the sermon outline on request, and converts any of them into EPUB or KEPUB for e-readers.

## What it does

- Builds one command per Google Drive file on the Linktree, so `/bulletin` (or `/bulletin_830_1045` and `/bulletin_2pm` when the church splits them) always points at the current week.
- Refreshes those commands every night at 00:00 Singapore time. Nobody has to run `/refresh` on Sunday morning.
- Serves the songbook from Linktree and the sermon outline (PDF or Word) from the Drive folder.
- Converts PDFs and Word files to EPUB or KEPUB sized for a chosen Kobo, Kindle-class reader or phone. See [E-reader downloads](#e-reader-downloads).
- Caches downloads and Telegram file ids so repeat requests are instant.
- Forwards `/report` messages, error alerts and refresh summaries to the maintainer's chat.

## Commands

| Command | What you get |
| --- | --- |
| `/bulletin`, `/bulletin_830_1045`, `/bulletin_2pm` | This week's bulletin PDF. Which commands exist depends on what Linktree lists. |
| `/songbook` | The Open Worship songbook PDF. |
| `/outline` | This week's sermon outline as PDF. |
| `/outline_doc` | This week's sermon outline as Word. |
| `/ebook` | Pick a file, a device and a format; receive an EPUB or KEPUB. |
| `/report <note>` | Send a bug report to the maintainer. Without a note, the bot asks for one. |
| `/help` | What the bot does and how to use it. |
| `/refresh` | Maintainer only. Re-read Linktree now and rebuild the file commands. |

## E-reader downloads

Every PDF or Word file the bot sends has an "E-reader version" button under it. That button, or `/ebook`, runs three steps, each an inline keyboard that edits the same message:

1. File: any bulletin on Linktree, the songbook, or the sermon outline. The outline is converted from the Word file, which keeps headings, lists and verse numbers; the PDF is used only when the folder has no Word file.
2. Device: Kobo Clara BW, Clara Colour, Libra Colour, Sage, Elipsa 2E, a Kindle-class reader, or a phone. Images are resampled to that screen width and turned greyscale for black-and-white readers. The bot remembers the choice and offers it first next time.
3. Format, Kobo only: KEPUB for Kobo's own reader, or standard EPUB. Other devices skip this step and get EPUB.

Results are cached in `bulletin_cache/ebooks/` by source content, device and format, so each file is converted once per device per week.

How the PDF reader works: PyMuPDF gives every text line with its font, size, weight and position. Lines are merged into paragraphs by proximity, headings are picked by size and weight relative to the body text, and the bulletin's label-and-body column layout is recognised and read in order. Hyperlinks and embedded images are kept. Vertical gaps that outlines leave for handwritten notes become blank space of matching height. A page with no extractable text (a scan, a flattened design) is rendered as an image so it is not lost. Word files go through mammoth, and runs of empty paragraphs are kept as note space. Legacy `.doc` files cannot be converted.

The device table, EPUB package layout and stylesheet are adapted from [KoboForge](https://github.com/AlphaeusNg/KoboForge) by Alphaeus Ng. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Setup

You need a bot token from [@BotFather](https://t.me/BotFather), Docker for deployment, and Python 3.10 with [uv](https://docs.astral.sh/uv/) for local runs.

```bash
git clone https://github.com/markusyeo/BABulletinBotV2
cd BABulletinBotV2
cp .env.example .env
```

Fill in `.env`:

| Variable | Required | Meaning |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | yes | Token from BotFather. |
| `LINKTREE_URL` | yes | The church Linktree, for example `https://linktr.ee/bukitarangchurch`. |
| `OUTLINE_FOLDER_URL` | yes | Google Drive folder that holds the sermon outlines. |
| `ADMIN_CHAT_ID` | no | Your own chat with the bot. Receives `/report` messages, error alerts and nightly refresh summaries, and is the only chat allowed to run `/refresh`. Send the bot any message, then read the id from `getUpdates`, or set it after the first `/ebook` use from `bulletin_cache/bot_state.pickle`. |
| `TIMEZONE` | no | Zone for the nightly refresh. Default `Asia/Singapore`. |
| `AUTO_REFRESH_TIME` | no | Nightly refresh time as `HH:MM`. Default `00:00`. A failed run retries three times, ten minutes apart. |
| `EBOOK_AUTHOR` | no | Author written into generated EPUBs. Default `Bukit Arang Church`. |

## Run

Locally:

```bash
uv sync
uv run -m app.main
```

With Docker Compose:

```bash
docker compose up -d --build
docker compose logs -f
```

`bulletin_cache/` is mounted into the container and holds downloads, generated ebooks and the per-user settings file.

## Tests

```bash
uv run pytest
```

The tests build small PDFs on the fly, so they need no files from the church.
