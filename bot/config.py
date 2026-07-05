"""Application configuration loaded from environment variables / .env file."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration object.

    All values can be overridden via environment variables or a `.env` file
    located at the project root. See `.env.example` for documentation of
    every option.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Telegram ---
    bot_token: str = Field(..., alias="BOT_TOKEN")

    use_local_api: bool = Field(default=False, alias="USE_LOCAL_API")
    telegram_api_id: str = Field(default="", alias="TELEGRAM_API_ID")
    telegram_api_hash: str = Field(default="", alias="TELEGRAM_API_HASH")
    local_api_base_url: str = Field(
        default="http://telegram-bot-api:8081", alias="LOCAL_API_BASE_URL"
    )

    # --- Storage ---
    storage_dir: Path = Field(default=Path("./storage"), alias="STORAGE_DIR")

    # --- Limits ---
    max_input_size_mb: int = Field(default=2000, alias="MAX_INPUT_SIZE_MB")
    max_concurrent_jobs: int = Field(default=2, alias="MAX_CONCURRENT_JOBS")
    default_target_size_mb: int = Field(default=50, alias="DEFAULT_TARGET_SIZE_MB")

    # --- Binaries ---
    ffmpeg_bin: str = Field(default="ffmpeg", alias="FFMPEG_BIN")
    ffprobe_bin: str = Field(default="ffprobe", alias="FFPROBE_BIN")

    # --- Logging ---
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("storage_dir", mode="after")
    @classmethod
    def _ensure_storage_dir_exists(cls, value: Path) -> Path:
        value.mkdir(parents=True, exist_ok=True)
        return value

    @field_validator("max_concurrent_jobs", mode="after")
    @classmethod
    def _hard_cap_single_job(cls, value: int) -> int:
        """Hard safety limit: never allow more than one ffmpeg job to run
        at the same time, no matter what is configured via the
        MAX_CONCURRENT_JOBS environment variable. Running more than one
        heavy ffmpeg encode concurrently risks exhausting CPU/RAM and
        crashing the host, so this is intentionally not adjustable upward.
        Everyone else waits in a queue (see bot/services/queue_tracker.py).
        """
        return 1 if value > 1 or value < 1 else value

    @property
    def max_input_size_bytes(self) -> int:
        return self.max_input_size_mb * 1024 * 1024

    @property
    def telegram_file_size_limit_bytes(self) -> int:
        """Effective inbound file-size limit given the current API mode."""
        if self.use_local_api:
            return self.max_input_size_bytes
        # Official cloud Bot API caps file downloads at 20 MB.
        return 20 * 1024 * 1024


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = load_settings()
