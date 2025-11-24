# BABulletinBot_v2

A Telegram bot that fetches the weekly Sunday Bulletin from the Bukit Arang Church Linktree and serves it to users.

## Features

- Fetches the latest "Sunday Bulletin" from Linktree.
- Downloads Songbook PDFs from Linktree.
- Retrieves Sermon Outlines (PDF and DOCX) from Google Drive folders.
- Handles Google Drive links (converts view links to download links).
- Caches files locally to avoid redundant downloads.
- Validates cache using URL checksums.
- Appends the Sunday date to bulletin filenames.
- File ID caching for faster re-sends on Telegram.

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

## Running Locally

1.  **Install dependencies:**

    ```bash
    uv sync
    ```

2.  **Run the bot:**
    ```bash
    uv run ./app/main.py
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
- `/bulletin`: Download and receive the latest Sunday Bulletin.
- `/songbook`: Download and receive the latest Songbook.
- `/outline`: Download the Sermon Outline (PDF format).
- `/outline_doc`: Download the Sermon Outline (DOCX format).

## Credits

This project was built with [Antigravity](https://github.com/google-deepmind/antigravity).
