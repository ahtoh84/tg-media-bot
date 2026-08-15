"""Command handlers for bot commands."""

from aiogram import Bot, types
from aiogram.fsm.context import FSMContext

from ..queue import get_queue_manager
from ..services.uploader import UploaderService
from ..types.download import MediaFormat
from ..utils.logger import get_logger

logger = get_logger()


# Supported platforms list
SUPPORTED_PLATFORMS = [
    "YouTube",
    "SoundCloud",
    "Vimeo",
    "TikTok",
    "Twitter/X",
    "Instagram",
    "Reddit",
    "Twitch",
    "And 1000+ more via yt-dlp",
]


class CommandHandlers:
    """Handlers for bot commands."""

    HELP_TEXT = """
<b>Media Downloader Bot</b>

Send me any media URL and I'll download and send it back to you.

<b>Commands:</b>

/start - Start the bot
/help - Show this help
/audio - Switch to audio-only mode (MP3)
/video - Switch to video download mode
/formats &lt;url&gt; - Pick a download quality (buttons)
/cancel &lt;task_id&gt; - Cancel a download
/status - Show your active downloads
/minimal on|off - Toggle minimal UI (no status messages, no caption on media)
/topic lock|unlock|status - Restrict the bot to one forum topic in this group

<b>Supported Platforms:</b>
"""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.queue = get_queue_manager()
        self.uploader = UploaderService(bot)

    async def cmd_start(self, message: types.Message):
        """Handle /start command."""
        await message.answer(
            "👋 Welcome to Media Downloader Bot!\n\n"
            "Send me a URL to download media.\n"
            "Use /help for all commands.",
            parse_mode="HTML",
        )

    async def cmd_help(self, message: types.Message):
        """Handle /help command."""
        platforms_text = "\n".join(f"• {p}" for p in SUPPORTED_PLATFORMS)
        await message.answer(
            self.HELP_TEXT + platforms_text,
            parse_mode="HTML",
        )

    async def cmd_audio(self, message: types.Message):
        """Handle /audio command - set audio-only mode."""
        from ..bot.handlers import get_handlers, DownloadState

        user_id = message.from_user.id
        handlers = get_handlers(self.bot)
        user_state = handlers.get_user_state(user_id)
        user_state.preferred_format = MediaFormat.AUDIO

        await message.answer("🎵 Audio-only mode enabled. Downloads will be converted to MP3.")

    async def cmd_video(self, message: types.Message):
        """Handle /video command - set video mode."""
        from ..bot.handlers import get_handlers

        user_id = message.from_user.id
        handlers = get_handlers(self.bot)
        user_state = handlers.get_user_state(user_id)
        user_state.preferred_format = MediaFormat.VIDEO

        await message.answer("🎬 Video mode enabled. Downloads will include video when available.")

    async def cmd_cancel(self, message: types.Message):
        """Handle /cancel command."""
        user_id = message.from_user.id
        args = message.text.split()[1:] if len(message.text.split()) > 1 else []

        if not args:
            await message.answer(
                "Usage: /cancel &lt;task_id&gt;\n\n"
                "Use /status to see active task IDs."
            )
            return

        task_id = args[0]
        from ..bot.handlers import get_handlers
        success = get_handlers(self.bot).cancel_download(task_id, user_id)

        if success:
            await message.answer(f"✅ Task {task_id} cancelled.")
        else:
            await message.answer(
                f"❌ Could not cancel task {task_id}.\n"
                "Make sure the task is yours and still active."
            )

    async def cmd_status(self, message: types.Message):
        """Handle /status command."""
        user_id = message.from_user.id
        summary = self.queue.get_status_summary(user_id)

        await message.answer(f"📊 Your Downloads:\n\n{summary}")

    async def cmd_minimal(self, message: types.Message):
        """Handle /minimal command - toggle minimal UI mode for this chat.

        In minimal mode, downloads produce no queued/progress/"Done!" status
        messages and the uploaded media carries no title/source-URL caption —
        just the file itself. Failures are still reported.
        """
        from ..services.minimal_store import get_minimal_store

        store = get_minimal_store()
        chat_id = message.chat.id
        args = message.text.split()[1:] if len(message.text.split()) > 1 else []

        if not args:
            enabled = store.contains(chat_id)
            await message.answer(
                f"Minimal UI mode is currently {'ON' if enabled else 'OFF'} for this chat.\n"
                "Usage: /minimal on|off"
            )
            return

        choice = args[0].lower()
        if choice not in ("on", "off"):
            await message.answer("Usage: /minimal on|off")
            return

        store.set(chat_id, choice == "on")
        if choice == "on":
            await message.answer(
                "🤫 Minimal UI mode enabled. Downloads will be sent with no "
                "status messages and no caption."
            )
        else:
            await message.answer("✅ Minimal UI mode disabled. Normal status messages and captions restored.")

    async def cmd_topic(self, message: types.Message):
        """Handle /topic — restrict the bot to one forum topic in this group.

        /topic lock, sent from inside the desired topic, confines the bot to
        that topic in this chat; every other topic (including "General") is
        then ignored. /topic unlock lifts it. /topic itself is always
        reachable regardless of the current lock, so a chat can't get stuck.
        """
        from ..services.topic_lock import get_topic_lock_store

        chat = message.chat
        if chat.type not in ("group", "supergroup"):
            await message.answer("Topic locking only applies to group chats with forum topics enabled.")
            return

        store = get_topic_lock_store()
        args = message.text.split()[1:] if len(message.text.split()) > 1 else []
        action = args[0].lower() if args else "status"

        if action == "lock":
            if not message.is_topic_message:
                await message.answer(
                    "Send /topic lock from inside the topic you want the bot restricted to "
                    "(this was sent outside a topic, e.g. in \"General\")."
                )
                return
            store.set(chat.id, message.message_thread_id)
            await message.answer(
                f"🔒 Bot restricted to this topic (id {message.message_thread_id}) in this group.\n"
                "Other topics, including General, are now ignored. /topic unlock to undo."
            )
        elif action == "unlock":
            store.clear(chat.id)
            await message.answer("🔓 Topic restriction removed — the bot now responds in every topic here.")
        elif action == "status":
            locked = store.get(chat.id)
            if locked is None:
                await message.answer("No topic restriction set for this group.")
            else:
                await message.answer(f"🔒 Restricted to topic id {locked}.")
        else:
            await message.answer("Usage: /topic lock|unlock|status")

    async def cmd_formats(self, message: types.Message):
        """Handle /formats — show an inline quality picker for a URL."""
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        from ..bot.handlers import get_handlers
        from ..bot.quality import QUALITY_CHOICES

        # Get URL from message text
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.answer(
                "Usage: /formats &lt;url&gt;\n\n"
                "Example: /formats https://youtube.com/watch?v=..."
            )
            return

        url = parts[1].strip()
        handlers = get_handlers(self.bot)

        if not handlers.downloader.validate_url(url):
            await message.answer("❌ Invalid URL.")
            return

        token = handlers.stash_url(url)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"q:{token}:{value}")]
            for label, value in QUALITY_CHOICES
        ])
        await message.answer("🎚️ Choose a quality:", reply_markup=keyboard)
