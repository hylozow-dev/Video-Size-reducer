"""Entrypoint: wires up the Bot, Dispatcher, routers and starts polling."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.handlers import admin, common, video
from bot.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def _build_bot() -> Bot:
    session: AiohttpSession | None = None

    if settings.use_local_api:
        api_server = TelegramAPIServer.from_base(settings.local_api_base_url, is_local=True)
        session = AiohttpSession(api=api_server)
        logger.info("Using local Bot API server at %s", settings.local_api_base_url)
    else:
        logger.info(
            "Using the official Bot API (cloud). Inbound files are limited to 20 MB."
        )

    return Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def _build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(common.router)
    dp.include_router(admin.router)
    dp.include_router(video.router)
    return dp


async def _run() -> None:
    setup_logging(settings.log_level)
    logger.info("Starting Video Size Reducer bot...")
    logger.info("Storage directory: %s", settings.storage_dir)
    logger.info("Max concurrent ffmpeg jobs: %s", settings.max_concurrent_jobs)

    bot = _build_bot()
    dp = _build_dispatcher()

    try:
        me = await bot.get_me()
        logger.info("Authorized as @%s (id=%s)", me.username, me.id)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to authenticate with Telegram. Check BOT_TOKEN.")
        raise

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


def main() -> None:
    try:
        asyncio.run(_run())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")


if __name__ == "__main__":
    main()
