# BABulletinBot_v2

A Telegram bot that fetches the weekly Sunday Bulletin from the Bukit Arang Church Linktree and serves it to users.

## Features

- Fetches the latest "Sunday Bulletin" from [Linktree](REDACTED_LINKTREE_URL).
- Handles Google Drive links (converts view links to download links).
- Caches the bulletin locally to avoid redundant downloads.
- Validates cache using URL checksums.
- Appends the Sunday date to the filename.

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
    Copy the example environment file and fill in your Telegram Bot Token.
    ```bash
    cp .env.example .env
    ```
    Open `.env` and set your token:
    ```
    TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
    ```

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

- `/start`: Welcome message.
- `/help`: Show available commands.
- `/bulletin`: Download and receive the latest Sunday Bulletin.

## Credits

This project was built with [Antigravity](https://github.com/google-deepmind/antigravity).
