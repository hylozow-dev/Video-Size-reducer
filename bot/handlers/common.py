"""Basic commands: /start, /help, /cancel."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

router = Router(name="common")


WELCOME_TEXT = (
    "👋 <b>Video Size Reducer Bot</b>\n\n"
    "Send me a video (or a video sent as a file/document) and I'll compress it "
    "with <b>ffmpeg</b> and send the result back.\n\n"
    "After you send a video you'll be able to choose:\n"
    "• A quality preset (quick, no guesswork), or\n"
    "• An exact target file size in MB (e.g. for platforms with upload limits)\n\n"
    "Send /help for more details, or just send a video to get started."
)

HELP_TEXT = (
    "<b>How to use this bot</b>\n\n"
    "1. Send a video file (as a video or a document).\n"
    "2. Pick a compression option:\n"
    "   🟢 High quality — smallest quality loss\n"
    "   🟡 Balanced — good quality/size trade-off\n"
    "   🔴 Smallest size — strongest compression\n"
    "   🎯 Custom target size — tell me the size in MB you want\n"
    "3. Wait for processing — I'll show progress as I go.\n"
    "4. Receive your compressed video!\n\n"
    "Use /cancel at any time to abort an in-progress selection.\n\n"
    "<i>Note:</i> depending on how this bot is deployed, there may be a limit "
    "on how large a video you can upload. If your video is rejected as too "
    "large, ask the bot operator about enabling the local Bot API server."
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(WELCOME_TEXT)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer("Nothing to cancel.")
        return
    await state.clear()
    await message.answer("Cancelled.")
