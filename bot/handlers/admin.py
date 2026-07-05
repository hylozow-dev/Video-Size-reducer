"""Admin panel: user management and video request inspection."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import settings
from bot.services.user_store import get_all_users, get_user_requests
from bot.utils.formatting import human_size

logger = logging.getLogger(__name__)

router = Router(name="admin")

# Callback data prefixes (kept short to stay under 64 bytes)
CB_USERS_PAGE = "adm:upage:"
CB_MANAGE_USER = "adm:usr:"
CB_USER_REQS_PAGE = "adm:rpage:"
CB_SEND_VIDEO = "adm:vid:"
CB_BACK_USERS = "adm:back"

USERS_PER_PAGE = 10
REQUESTS_PER_PAGE = 10


def _is_admin(user_id: int) -> bool:
    return user_id in settings.admin_user_ids


def _user_display_name(user: dict) -> str:
    """Build a display name from user record."""
    parts = []
    if user.get("first_name"):
        parts.append(user["first_name"])
    if user.get("username"):
        parts.append(f"@{user['username']}")
    if not parts:
        parts.append(str(user["user_id"]))
    return " ".join(parts)


def _build_users_keyboard(page: int) -> InlineKeyboardMarkup:
    """Build paginated user list keyboard."""
    users = get_all_users()
    total = len(users)
    total_pages = max(1, (total + USERS_PER_PAGE - 1) // USERS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    start = page * USERS_PER_PAGE
    end = start + USERS_PER_PAGE
    page_users = users[start:end]

    rows: list[list[InlineKeyboardButton]] = []
    for user in page_users:
        uid = user["user_id"]
        name = _user_display_name(user)
        rows.append([
            InlineKeyboardButton(
                text=f"{uid} - {name}",
                callback_data=f"{CB_MANAGE_USER}{uid}:0",
            ),
        ])

    # Pagination row
    nav_buttons: list[InlineKeyboardButton] = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="⬅️ Prev", callback_data=f"{CB_USERS_PAGE}{page - 1}")
        )
    nav_buttons.append(
        InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")
    )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="Next ➡️", callback_data=f"{CB_USERS_PAGE}{page + 1}")
        )
    if nav_buttons:
        rows.append(nav_buttons)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_requests_keyboard(user_id: int, page: int) -> tuple[str, InlineKeyboardMarkup]:
    """Build paginated video requests keyboard for a user."""
    requests = get_user_requests(user_id)
    total = len(requests)
    total_pages = max(1, (total + REQUESTS_PER_PAGE - 1) // REQUESTS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    start = page * REQUESTS_PER_PAGE
    end = start + REQUESTS_PER_PAGE
    page_requests = requests[start:end]

    rows: list[list[InlineKeyboardButton]] = []
    for idx, req in enumerate(page_requests):
        global_idx = start + idx
        fname = req.get("filename", "video")
        size_str = human_size(req["file_size"]) if req.get("file_size") else "?"
        ts = req.get("timestamp", 0)
        dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        label = f"{fname} ({size_str}) - {dt_str}"
        # Trim label if too long for display
        if len(label) > 50:
            label = label[:47] + "..."
        rows.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"{CB_SEND_VIDEO}{user_id}:{global_idx}",
            ),
        ])

    # Pagination row
    nav_buttons: list[InlineKeyboardButton] = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(
                text="⬅️ Prev",
                callback_data=f"{CB_USER_REQS_PAGE}{user_id}:{page - 1}",
            )
        )
    nav_buttons.append(
        InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")
    )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text="Next ➡️",
                callback_data=f"{CB_USER_REQS_PAGE}{user_id}:{page + 1}",
            )
        )
    if nav_buttons:
        rows.append(nav_buttons)

    # Back button
    rows.append([
        InlineKeyboardButton(text="🔙 Back to users", callback_data=CB_BACK_USERS)
    ])

    header = f"Video requests for user <b>{user_id}</b> ({total} total):"
    return header, InlineKeyboardMarkup(inline_keyboard=rows)


# --- Handlers ---


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("Access denied.")
        return

    users = get_all_users()
    text = f"👤 <b>User Management</b>\n\nTotal users: {len(users)}"
    await message.answer(text, reply_markup=_build_users_keyboard(0))


@router.callback_query(F.data.startswith(CB_USERS_PAGE))
async def handle_users_page(callback: CallbackQuery) -> None:
    if not callback.from_user or not _is_admin(callback.from_user.id):
        await callback.answer("Access denied.", show_alert=True)
        return

    page_str = (callback.data or "").removeprefix(CB_USERS_PAGE)
    try:
        page = int(page_str)
    except ValueError:
        page = 0

    users = get_all_users()
    text = f"👤 <b>User Management</b>\n\nTotal users: {len(users)}"

    if callback.message:
        await callback.message.edit_text(text, reply_markup=_build_users_keyboard(page))
    await callback.answer()


@router.callback_query(F.data.startswith(CB_MANAGE_USER))
async def handle_manage_user(callback: CallbackQuery) -> None:
    if not callback.from_user or not _is_admin(callback.from_user.id):
        await callback.answer("Access denied.", show_alert=True)
        return

    raw = (callback.data or "").removeprefix(CB_MANAGE_USER)
    parts = raw.split(":")
    try:
        user_id = int(parts[0])
        page = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        await callback.answer("Invalid data.", show_alert=True)
        return

    header, keyboard = _build_requests_keyboard(user_id, page)

    if callback.message:
        await callback.message.edit_text(header, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith(CB_USER_REQS_PAGE))
async def handle_requests_page(callback: CallbackQuery) -> None:
    if not callback.from_user or not _is_admin(callback.from_user.id):
        await callback.answer("Access denied.", show_alert=True)
        return

    raw = (callback.data or "").removeprefix(CB_USER_REQS_PAGE)
    parts = raw.split(":")
    try:
        user_id = int(parts[0])
        page = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        await callback.answer("Invalid data.", show_alert=True)
        return

    header, keyboard = _build_requests_keyboard(user_id, page)

    if callback.message:
        await callback.message.edit_text(header, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith(CB_SEND_VIDEO))
async def handle_send_video(callback: CallbackQuery, bot: Bot) -> None:
    if not callback.from_user or not _is_admin(callback.from_user.id):
        await callback.answer("Access denied.", show_alert=True)
        return

    raw = (callback.data or "").removeprefix(CB_SEND_VIDEO)
    parts = raw.split(":")
    try:
        user_id = int(parts[0])
        req_idx = int(parts[1])
    except (ValueError, IndexError):
        await callback.answer("Invalid data.", show_alert=True)
        return

    requests = get_user_requests(user_id)
    if req_idx < 0 or req_idx >= len(requests):
        await callback.answer("Request not found.", show_alert=True)
        return

    req = requests[req_idx]
    file_id = req["file_id"]

    try:
        await bot.send_video(
            chat_id=callback.from_user.id,
            video=file_id,
            caption=f"From user {user_id}\n{req.get('filename', 'video')}",
        )
        await callback.answer("Video sent!")
    except Exception as exc:
        logger.error("Failed to send video to admin: %s", exc)
        # Try as document fallback
        try:
            await bot.send_document(
                chat_id=callback.from_user.id,
                document=file_id,
                caption=f"From user {user_id}\n{req.get('filename', 'video')}",
            )
            await callback.answer("Video sent as document!")
        except Exception as exc2:
            logger.error("Failed to send as document too: %s", exc2)
            await callback.answer("Failed to send the video.", show_alert=True)


@router.callback_query(F.data == CB_BACK_USERS)
async def handle_back_to_users(callback: CallbackQuery) -> None:
    if not callback.from_user or not _is_admin(callback.from_user.id):
        await callback.answer("Access denied.", show_alert=True)
        return

    users = get_all_users()
    text = f"👤 <b>User Management</b>\n\nTotal users: {len(users)}"

    if callback.message:
        await callback.message.edit_text(text, reply_markup=_build_users_keyboard(0))
    await callback.answer()


@router.callback_query(F.data == "noop")
async def handle_noop(callback: CallbackQuery) -> None:
    await callback.answer()
