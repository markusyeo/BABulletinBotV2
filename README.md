# BABulletinBot_v2

A Telegram bot that fetches the weekly Sunday Bulletin from the Bukit Arang Church Linktree and serves it to users.

## Features

- Refreshes file commands dynamically from Linktree.
- Resolves Linktree redirects concurrently during refresh for faster command updates.
- Resolves short URLs such as `tiny.cc` before checking for Google Drive files.
- Downloads Songbook PDFs from Linktree.
- Retrieves Sermon Outlines (PDF and DOCX) from Google Drive folders.
- Handles Google Drive links (converts view links to download links).
- Caches files locally to avoid redundant downloads.
- Validates cache using URL checksums.
- Appends the Sunday date to bulletin filenames.
- File ID caching for faster re-sends on Telegram.
- Refreshes the file commands from Linktree on a schedule (daily at 00:00 Singapore time by default), so the new week's bulletin appears without a manual `/refresh`.
- Converts any PDF or DOCX it serves into EPUB or KEPUB sized for a chosen e-reader, with the result cached on disk. See [E-reader downloads](#e-reader-downloads).

## Prerequisites

- Docker (for containerized deployment)
- Python 3.10+ (for local development)
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

## Setup & Configuration

1.  **Clone the repository:**

    ```bash
    git clone <repository_url>
    cd BABulletinBotV2
    ```

2.  **Environment Variables:**
    Copy the example environment file and fill in the required values.

    ```bash
    cp .env.example .env
    ```

    Open `.env` and set the following variables:

    ```
    TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
    LINKTREE_URL=https://linktr.ee/your_linktree_username
    OUTLINE_FOLDER_URL=https://drive.google.com/drive/folders/your_folder_id
    ```

    **Required Environment Variables:**

    - `TELEGRAM_BOT_TOKEN`: Your Telegram bot token from [@BotFather](https://t.me/BotFather)
    - `LINKTREE_URL`: The URL to your Linktree page (e.g., `https://linktr.ee/your_username`)
    - `OUTLINE_FOLDER_URL`: The Google Drive folder URL containing sermon outlines (e.g., `https://drive.google.com/drive/folders/your_folder_id`)

    **Optional Environment Variables:**

    - `TIMEZONE`: Zone for the scheduled refresh. Default `Asia/Singapore`.
    - `AUTO_REFRESH_TIME`: Daily refresh time as `HH:MM` in `TIMEZONE`. Default `00:00`. A failed run retries every 10 minutes, three times.
    - `ADMIN_CHAT_ID`: Telegram chat id that receives a one-line summary after each scheduled refresh. Unset means no message.
    - `EBOOK_AUTHOR`: Author written into generated EPUB metadata. Default `Bukit Arang Church`.

## Running Locally

1.  **Install dependencies:**

    ```bash
    uv sync
    ```

2.  **Run the bot:**
    ```bash
    uv run -m app.main
    ```

## Deploying with Docker Compose

1.  **Build and run the container:**

    ```bash
    docker-compose up -d --build
    ```

2.  **Verify it's running:**

    ```bash
    docker-compose ps
    docker-compose logs -f
    ```

3.  **Stop the bot:**
    ```bash
    docker-compose down
    ```

## Commands

- `/start`: Welcome message with bot information and Linktree link.
- `/help`: Show available commands.
- `/refresh`: Re-scrape Linktree, resolve every page link to its final URL, and rebuild commands for Google Drive-backed files.
- `/bulletin`: Download the latest Sunday Bulletin when Linktree has one shared bulletin.
- `/bulletin_830_1045`: Download the latest 8.30/10.45am Gathering Bulletin when Linktree has a split bulletin.
- `/bulletin_2pm`: Download the latest 2pm Gathering Bulletin when Linktree has a split bulletin.
- `/songbook`: Download and receive the latest Songbook.
- `/outline`: Download the Sermon Outline (PDF format).
- `/outline_doc`: Download the Sermon Outline (DOCX format).
- `/ebook`: Pick a file, a device and a format, and receive it as EPUB or KEPUB.

## E-reader downloads

Every PDF or DOCX the bot sends carries an **E-reader version** button. Tapping it, or running `/ebook`, walks through three inline-keyboard steps:

1. **File**: any bulletin currently on Linktree, the songbook, or the sermon outline.
2. **Device**: Kobo Clara BW, Clara Colour, Libra Colour, Sage, Elipsa 2E, a generic Kindle-sized reader, or a phone. Images are resampled to that screen's width and converted to greyscale for black-and-white readers. The choice is remembered per user and offered first next time.
3. **Format** (Kobo only): KEPUB for Kobo's native reader, or standard EPUB. Non-Kobo devices skip this step and get EPUB.

Conversions are cached under `bulletin_cache/ebooks/` keyed by source content, device and format, so a file is converted once per week per device.

The PDF reader works from PyMuPDF's font-aware line geometry rather than raw text extraction: it merges wrapped lines into paragraphs, picks headings by size and weight, recognises the bulletin's label-and-body column layout, keeps hyperlinks and embedded images, and renders any page with no extractable text (scans, flattened designs) as an image so nothing disappears. DOCX goes through mammoth. Legacy `.doc` files are not convertible.

The device table, package layout and stylesheet are adapted from [KoboForge](https://github.com/AlphaeusNg/KoboForge) by Alphaeus Ng. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Tests

```bash
uv run pytest
```
