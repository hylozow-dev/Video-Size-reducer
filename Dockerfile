FROM python:3.12-slim AS base

# ffmpeg provides both `ffmpeg` and `ffprobe` binaries
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/storage \
    && chown -R appuser:appuser /app

USER appuser

ENV PYTHONUNBUFFERED=1 \
    STORAGE_DIR=/app/storage

VOLUME ["/app/storage"]

ENTRYPOINT ["python", "-m", "bot.main"]
