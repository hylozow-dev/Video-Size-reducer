"""Inline keyboards used by the bot."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.ffmpeg_service import Preset

CB_PRESET_PREFIX = "preset:"
CB_CUSTOM_SIZE = "custom_size"
CB_CANCEL = "cancel"


def compression_mode_keyboard() -> InlineKeyboardMarkup:
    """Build the compression-mode keyboard with colored buttons.

    Requires Bot API 9.4+ / aiogram 3.25.0+ for the `style` field. Telegram
    clients render the button's accent color (including its built-in
    indicator) based on `style`, so no manual colored emoji is needed:
        - "success" -> green   (High quality preset)
        - "primary" -> blue    (Balanced preset)
        - "danger"  -> red     (Smallest size preset)
    The "custom target size" and "cancel" buttons are left uncolored
    (style omitted -> app-specific default look).
    """
    rows = [
        [
            InlineKeyboardButton(
                text=Preset.HIGH.label,
                callback_data=f"{CB_PRESET_PREFIX}{Preset.HIGH.value}",
                style="success",
            )
        ],
        [
            InlineKeyboardButton(
                text=Preset.MEDIUM.label,
                callback_data=f"{CB_PRESET_PREFIX}{Preset.MEDIUM.value}",
                style="primary",
            )
        ],
        [
            InlineKeyboardButton(
                text=Preset.LOW.label,
                callback_data=f"{CB_PRESET_PREFIX}{Preset.LOW.value}",
                style="danger",
            )
        ],
        [
            InlineKeyboardButton(
                text="🎯 Set exact target size (MB)",
                callback_data=CB_CUSTOM_SIZE,
            )
        ],
        [InlineKeyboardButton(text="✖️ Cancel", callback_data=CB_CANCEL)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✖️ Cancel", callback_data=CB_CANCEL)]]
    )
