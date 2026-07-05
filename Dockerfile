FROM python:3.12-slim AS base

# ffmpeg provides both `ffmpeg` and `ffprobe` binaries
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot

# uid/gid 101 intentionally matches the "telegram-bot-api" user used by the
# aiogram/telegram-bot-api image. When running in local-api mode, that
# server writes downloaded files to a volume shared with this container
# (see docker-compose.yml); matching uid/gid lets this container's user read
# those files without needing to relax their permissions.
RUN groupadd --gid 101 appuser \
    && useradd --uid 101 --gid 101 --create-home --shell /bin/bash appuser \
    && mkdir -p /app/storage \
    && chown -R appuser:appuser /app

USER appuser

ENV PYTHONUNBUFFERED=1 \
    STORAGE_DIR=/app/storage

VOLUME ["/app/storage"]

ENTRYPOINT ["python", "-m", "bot.main"]
