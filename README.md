# Video Size Reducer Bot

A Telegram bot built with **Python** and **aiogram 3** that receives videos
from users, compresses them with **ffmpeg**, and sends the result back.

Supports videos up to **2 GB** when deployed with a self-hosted local
Telegram Bot API server (see below); otherwise it's limited by the official
cloud Bot API to 20 MB downloads / 50 MB uploads.

## Features

- Send a video (as a video message or a document/file) to the bot.
- Choose how to compress it:
  - 🟢 **High quality** preset (CRF 20)
  - 🟡 **Balanced** preset (CRF 26)
  - 🔴 **Smallest size** preset (CRF 32)
  - 🎯 **Custom target size** in MB — the bot computes the bitrate needed to
    hit that size given the video's duration
- Live progress updates while ffmpeg encodes.
- Automatic downscale cap at 1080p to help hit smaller targets.
- **Strict single-job processing**: the bot compresses exactly one video at
  a time, no matter how many users send videos simultaneously, to avoid
  overloading the host. Everyone else is placed in a FIFO queue and is told
  their position and an estimated wait time (based on the active job's real
  progress once available), then is served automatically in order.
- Automatic cleanup of temporary files after each job.
- Works with or without a local Bot API server.

## Project layout

```
bot/
  main.py                 # Entrypoint: builds Bot/Dispatcher, starts polling
  config.py               # Settings loaded from environment / .env
  logging_setup.py        # Logging configuration
  states.py               # aiogram FSM states
  keyboards.py            # Inline keyboards
  handlers/
    common.py             # /start, /help, /cancel
    video.py              # Video intake + compression flow
  services/
    media_info.py         # ffprobe wrapper
    ffmpeg_service.py      # ffmpeg compression logic (presets + target size)
    queue_tracker.py       # Single-job queue + wait-time estimation
  utils/
    formatting.py         # Human-readable sizes/durations/progress bars
    tempfiles.py          # Per-job temp directory management
requirements.txt
Dockerfile
docker-compose.yml
.env.example
```

## Quick start (Docker, recommended)

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Copy the example environment file and fill in your token:

   ```bash
   cp .env.example .env
   # edit .env and set BOT_TOKEN=...
   ```

3. Start the bot:

   ```bash
   docker compose up -d --build
   ```

By default this runs in **cloud API mode**: simple, no extra setup, but
limited to downloading files up to 20 MB.

### Enabling large file support (up to 2 GB)

To accept larger videos, run a self-hosted [Telegram Bot API
server](https://github.com/tdlib/telegram-bot-api) alongside the bot:

1. Obtain an `api_id` and `api_hash` from <https://my.telegram.org> (under
   "API development tools").
2. In `.env`, set:

   ```
   USE_LOCAL_API=true
   TELEGRAM_API_ID=your_api_id
   TELEGRAM_API_HASH=your_api_hash
   ```

3. Start both services with the `local-api` profile:

   ```bash
   docker compose --profile local-api up -d --build
   ```

   The bot and the `telegram-bot-api` container share a Docker volume
   (`bot-storage`), so the bot can read files the local server already saved
   to disk without needing to re-download them over HTTP.

> **Note:** If your bot was previously used with the official cloud API, you
> may need to call `logOut` once before switching it to the local server (the
> official Telegram Bot API documentation covers this). For a fresh bot
> token, no extra step is needed.

## Running without Docker

Requirements: Python 3.11+, `ffmpeg`/`ffprobe` installed and on `PATH`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in BOT_TOKEN
python -m bot.main
```

## Configuration reference

All settings are read from environment variables (or a `.env` file). See
[`.env.example`](.env.example) for the full list with descriptions,
including:

| Variable | Purpose |
|---|---|
| `BOT_TOKEN` | Telegram bot token (required) |
| `USE_LOCAL_API` | Enable local Bot API server mode |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | Required only when `USE_LOCAL_API=true` |
| `LOCAL_API_BASE_URL` | Base URL of the local Bot API server |
| `STORAGE_DIR` | Where downloaded/processed files are kept temporarily |
| `MAX_INPUT_SIZE_MB` | Hard cap on accepted input file size |
| `MAX_CONCURRENT_JOBS` | Documentational only — always hard-clamped to `1` in code (see below) |
| `FFMPEG_BIN` / `FFPROBE_BIN` | Override binary paths if not on `PATH` |
| `LOG_LEVEL` | Logging verbosity |

## Single-job queue behavior

To keep the host from being overloaded, the bot **never** runs more than
one ffmpeg compression job at a time, regardless of `MAX_CONCURRENT_JOBS`
(that value is clamped to `1` in `bot/config.py`, and the job semaphore in
`bot/handlers/video.py` also hardcodes `1` directly as a second safety
net).

If a user sends a video while another job is already running:
1. They're placed at the back of an in-memory FIFO queue.
2. They immediately receive a message telling them how many people are
   ahead of them and an estimated wait time.
3. The estimate is refined using the active job's real ffmpeg progress
   once it's available (before that, a rough flat fallback is used).
4. As soon as it's their turn, their video starts processing automatically
   — no further action needed from the user.

This queue is in-memory and per-process: if the bot restarts, any users
who were queued will need to resend their video.

## How target-size compression works

Given a desired output size and the video's duration, the bot computes an
average video bitrate:

```
video_kbps = (target_size_MB * 8192 * 0.98) / duration_sec - audio_kbps
```

It then encodes with `libx264` using `-b:v`/`-maxrate`/`-bufsize` to keep the
output close to (and safely under) the requested size, reserving a small
margin for container overhead. If the requested size is unrealistically
small for the video's length, the bot tells the user the minimum viable
target size instead of silently failing.

## License

This project is licensed under the [MIT License](LICENSE).

## Contact

Telegram: [@hylozo](https://t.me/hylozo)
