"""Main conversation flow: receive a video, ask how to compress it, process it."""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramEntityTooLarge
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from bot.config import settings
from bot.keyboards import (
    CB_CANCEL,
    CB_CUSTOM_SIZE,
    CB_PRESET_PREFIX,
    cancel_keyboard,
    compression_mode_keyboard,
)
from bot.services.user_store import record_user, record_video_request
from bot.services.ffmpeg_service import (
    CompressionError,
    Preset,
    compress_video,
    plan_for_preset,
    plan_for_target_size,
)
from bot.services.media_info import ProbeError, probe_video
from bot.services.queue_tracker import queue_tracker
from bot.states import CompressStates
from bot.utils.formatting import (
    human_duration,
    human_size,
    human_wait_estimate,
    progress_bar,
    reduction_percent,
)
from bot.utils.tempfiles import cleanup_job_dir, job_dir, new_job_id

logger = logging.getLogger(__name__)

router = Router(name="video")

# HARD LIMIT: exactly one ffmpeg job runs at a time, no matter what.
# settings.max_concurrent_jobs is clamped to 1 in bot/config.py, but the
# literal 1 is used directly here too so this guarantee can never regress
# even if that clamp is ever loosened by mistake.
_job_semaphore = asyncio.Semaphore(1)

_VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".3gp", ".ts")


def _looks_like_video_document(message: Message) -> bool:
    doc = message.document
    if doc is None:
        return False
    if doc.mime_type and doc.mime_type.startswith("video/"):
        return True
    if doc.file_name and doc.file_name.lower().endswith(_VIDEO_EXTENSIONS):
        return True
    return False


class ProgressReporter:
    """Throttled wrapper around message editing to avoid Telegram rate limits."""

    def __init__(self, bot: Bot, chat_id: int, message_id: int, prefix: str, min_interval: float = 2.5):
        self._bot = bot
        self._chat_id = chat_id
        self._message_id = message_id
        self._prefix = prefix
        self._min_interval = min_interval
        self._last_sent = 0.0
        self._last_text: Optional[str] = None

    async def update(self, fraction: float) -> None:
        now = time.monotonic()
        if now - self._last_sent < self._min_interval and fraction < 1.0:
            return
        text = f"{self._prefix}\n{progress_bar(fraction)}"
        if text == self._last_text:
            return
        self._last_sent = now
        self._last_text = text
        try:
            await self._bot.edit_message_text(
                chat_id=self._chat_id, message_id=self._message_id, text=text
            )
        except TelegramBadRequest:
            # Message content identical or message no longer editable; ignore.
            pass


async def _extract_incoming_video(message: Message) -> tuple[str, str, Optional[int]]:
    """Return (file_id, suggested_filename, file_size) for a video/document message."""
    if message.video:
        v = message.video
        filename = v.file_name or "video.mp4"
        return v.file_id, filename, v.file_size
    if message.document:
        d = message.document
        filename = d.file_name or "video.mp4"
        return d.file_id, filename, d.file_size
    raise ValueError("Message does not contain a supported video")


@router.message(F.video | (F.document & F.func(_looks_like_video_document)))
async def handle_incoming_video(message: Message, state: FSMContext) -> None:
    file_id, filename, file_size = await _extract_incoming_video(message)

    # Record user and video request for admin panel
    if message.from_user:
        record_user(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        record_video_request(
            user_id=message.from_user.id,
            file_id=file_id,
            filename=filename,
            file_size=file_size,
        )

    if file_size and file_size > settings.telegram_file_size_limit_bytes:
        limit_mb = settings.telegram_file_size_limit_bytes / (1024 * 1024)
        await message.answer(
            "⚠️ This file is too large for me to download right now "
            f"(limit: {limit_mb:.0f} MB).\n\n"
            + (
                ""
                if settings.use_local_api
                else "Ask the bot operator to enable the local Bot API server "
                "to support files up to 2 GB."
            )
        )
        return

    await state.update_data(file_id=file_id, filename=filename, file_size=file_size)
    await state.set_state(CompressStates.choosing_mode)
    await message.answer(
        "🎬 Got your video"
        + (f" ({human_size(file_size)})" if file_size else "")
        + ".\n\nHow should I compress it?",
        reply_markup=compression_mode_keyboard(),
    )


@router.callback_query(CompressStates.choosing_mode, F.data == CB_CUSTOM_SIZE)
async def ask_target_size(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CompressStates.waiting_target_size)
    if callback.message:
        await callback.message.edit_text(
            "🎯 Send the target file size in <b>megabytes</b> (e.g. <code>25</code>).",
            reply_markup=cancel_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == CB_CANCEL)
async def cancel_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.edit_text("✖️ Cancelled. Send a new video to start again.")
    await callback.answer()


@router.callback_query(CompressStates.choosing_mode, F.data.startswith(CB_PRESET_PREFIX))
async def handle_preset_choice(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not callback.data or not callback.message:
        await callback.answer()
        return

    preset_value = callback.data.removeprefix(CB_PRESET_PREFIX)
    try:
        preset = Preset(preset_value)
    except ValueError:
        await callback.answer("Unknown option.", show_alert=True)
        return

    await callback.answer()
    data = await state.get_data()
    await state.clear()
    await _run_compression_job(
        bot=bot,
        chat_id=callback.message.chat.id,
        status_message_id=callback.message.message_id,
        file_id=data["file_id"],
        filename=data["filename"],
        original_size=data.get("file_size"),
        preset=preset,
        target_size_mb=None,
    )


@router.message(CompressStates.waiting_target_size, F.text)
async def handle_target_size_input(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = (message.text or "").strip().replace(",", ".")
    try:
        target_mb = float(raw)
        if target_mb <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "That doesn't look like a valid number. Please send the target size "
            "in megabytes, e.g. <code>25</code>.",
            reply_markup=cancel_keyboard(),
        )
        return

    data = await state.get_data()
    await state.clear()

    status = await message.answer("⏳ Starting...")
    await _run_compression_job(
        bot=bot,
        chat_id=message.chat.id,
        status_message_id=status.message_id,
        file_id=data["file_id"],
        filename=data["filename"],
        original_size=data.get("file_size"),
        preset=None,
        target_size_mb=target_mb,
    )


async def _run_compression_job(
    *,
    bot: Bot,
    chat_id: int,
    status_message_id: int,
    file_id: str,
    filename: str,
    original_size: Optional[int],
    preset: Optional[Preset],
    target_size_mb: Optional[float],
) -> None:
    async def set_status(text: str) -> None:
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=status_message_id, text=text)
        except TelegramBadRequest:
            pass

    # The bot processes exactly one video at a time (see _job_semaphore
    # above), to avoid overloading the host. Anyone arriving while a job is
    # already running is placed in a FIFO queue and told roughly how long
    # they'll have to wait, based on the currently active job's progress.
    queue_position: Optional[int] = None
    if queue_tracker.is_busy:
        queue_position = queue_tracker.enter_queue()
        wait_estimate = queue_tracker.estimate_wait_seconds_for_position(queue_position)
        people_ahead = queue_position - 1
        ahead_note = (
            f" ({people_ahead} other{'s' if people_ahead != 1 else ''} ahead of you)"
            if people_ahead
            else ""
        )
        await set_status(
            "⏳ <b>Someone else's video is currently being processed.</b>\n"
            f"You're in the queue{ahead_note}.\n"
            f"Estimated wait: <b>{human_wait_estimate(wait_estimate)}</b>.\n\n"
            "I'll start on your video automatically as soon as it's your turn."
        )

    async with _job_semaphore:
        if queue_position is not None:
            queue_tracker.leave_queue()
        queue_tracker.start_job()

        job_id = new_job_id()
        jdir = job_dir(settings.storage_dir, job_id)
        input_path = jdir / f"input_{Path(filename).name}"
        output_path = jdir / "output.mp4"

        try:
            await set_status("⬇️ Downloading video...")
            await bot.download(file_id, destination=input_path)

            await set_status("🔍 Analyzing video...")
            try:
                info = await probe_video(input_path, settings.ffprobe_bin)
            except ProbeError as exc:
                logger.warning("Probe failed for job %s: %s", job_id, exc)
                await set_status(
                    "❌ I couldn't read this file as a video. It may be corrupted "
                    "or in an unsupported format."
                )
                return

            queue_tracker.set_video_duration(info.duration_sec)

            try:
                if preset is not None:
                    plan = plan_for_preset(preset)
                else:
                    assert target_size_mb is not None
                    plan = plan_for_target_size(info, target_size_mb)
            except ValueError as exc:
                await set_status(f"⚠️ {exc}")
                return

            reporter = ProgressReporter(
                bot=bot,
                chat_id=chat_id,
                message_id=status_message_id,
                prefix=f"🛠 Compressing ({human_duration(info.duration_sec)} video)...",
            )
            await set_status(f"🛠 Compressing...\n{progress_bar(0)}")

            queue_tracker.mark_compression_started()

            async def on_progress(fraction: float) -> None:
                queue_tracker.update_progress(fraction)
                await reporter.update(fraction)

            try:
                await compress_video(
                    input_path=input_path,
                    output_path=output_path,
                    plan=plan,
                    info=info,
                    ffmpeg_bin=settings.ffmpeg_bin,
                    on_progress=on_progress,
                )
            except CompressionError as exc:
                logger.error("Compression failed for job %s: %s", job_id, exc)
                await set_status("❌ Compression failed. Please try a different video or option.")
                return

            new_size = output_path.stat().st_size
            await set_status("⬆️ Uploading result...")

            caption = _build_result_caption(original_size, new_size, info.duration_sec)

            try:
                await bot.send_video(
                    chat_id=chat_id,
                    video=FSInputFile(output_path, filename=f"compressed_{Path(filename).stem}.mp4"),
                    caption=caption,
                    supports_streaming=True,
                )
            except TelegramEntityTooLarge:
                await set_status(
                    "❌ The compressed file is still too large to send with the current "
                    "bot configuration. Try a smaller target size or a stronger preset."
                )
                return
            except TelegramBadRequest as exc:
                logger.error("Failed to send result for job %s: %s", job_id, exc)
                await set_status("❌ Failed to send the compressed video.")
                return

            try:
                await bot.delete_message(chat_id=chat_id, message_id=status_message_id)
            except TelegramBadRequest:
                pass

        finally:
            cleanup_job_dir(settings.storage_dir, job_id)
            queue_tracker.finish_job()


def _build_result_caption(
    original_size: Optional[int], new_size: int, duration_sec: float
) -> str:
    lines = ["✅ <b>Done!</b>", f"Duration: {human_duration(duration_sec)}"]
    if original_size:
        pct = reduction_percent(original_size, new_size)
        lines.append(f"Size: {human_size(original_size)} → {human_size(new_size)} (-{pct:.0f}%)")
    else:
        lines.append(f"Size: {human_size(new_size)}")
    return "\n".join(lines)
