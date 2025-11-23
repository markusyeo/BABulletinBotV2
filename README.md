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
    uv run main.py
    ```

## Deploying with Docker

1.  **Build the Docker image:**

    ```bash
    docker build -t babulletinbot .
    ```

2.  **Run the Docker container:**
    Pass the environment variable directly or use the `.env` file.

    **Option A: Using `.env` file (Recommended)**

    ```bash
    docker run -d --name babulletinbot --env-file .env babulletinbot
    ```

    **Option B: Passing token directly**

    ```bash
    docker run -d --name babulletinbot -e TELEGRAM_BOT_TOKEN=your_token_here babulletinbot
    ```

3.  **Verify it's running:**
    ```bash
    docker ps
    docker logs babulletinbot
    ```

## Commands

- `/start`: Welcome message.
- `/help`: Show available commands.
- `/bulletin`: Download and receive the latest Sunday Bulletin.

## Credits

This project was built with [Antigravity](https://github.com/google-deepmind/antigravity).
