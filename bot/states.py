"""Finite State Machine states for the video-compression conversation flow."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class CompressStates(StatesGroup):
    # Waiting for the user to pick a preset or "custom size" after uploading a video.
    choosing_mode = State()
    # Waiting for the user to type a target size in MB.
    waiting_target_size = State()
