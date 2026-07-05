"""Inline keyboards used by the bot."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.ffmpeg_service import Preset

CB_PRESET_PREFIX = "preset:"
CB_CUSTOM_SIZE = "custom_size"
CB_CANCEL = "cancel"


def compression_mode_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"🟢 {Preset.HIGH.label}",
                callback_data=f"{CB_PRESET_PREFIX}{Preset.HIGH.value}",
            )
        ],
        [
            InlineKeyboardButton(
                text=f"🟡 {Preset.MEDIUM.label}",
                callback_data=f"{CB_PRESET_PREFIX}{Preset.MEDIUM.value}",
            )
        ],
        [
            InlineKeyboardButton(
                text=f"🔴 {Preset.LOW.label}",
                callback_data=f"{CB_PRESET_PREFIX}{Preset.LOW.value}",
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
