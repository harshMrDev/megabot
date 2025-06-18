import os
import sys
import logging
from datetime import datetime
from pyrogram import Client, idle, filters
from pyrogram.types import Message, BotCommand

# Constants
ADMIN_USERNAME = "harshMrDev"
START_TIME = "2025-06-18 14:52:11"

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize bot
app = Client(
    "youtube_downloader_bot",
    api_id=os.environ.get("API_ID"),
    api_hash=os.environ.get("API_HASH"),
    bot_token=os.environ.get("BOT_TOKEN"),
    plugins=dict(root="plugins")
)

# Command list
COMMANDS = [
    BotCommand("start", "Start the bot"),
    BotCommand("help", "Show help message"),
    BotCommand("ping", "Check bot response"),
    BotCommand("utube", "Download from YouTube"),
    BotCommand("m3u8", "Download M3U8 streams")
]

@app.on_message(filters.command(["start", "help"]) & filters.private)
async def start_command(client, message):
    """Start command handler"""
    await message.reply_text(
        f"👋 Hello {message.from_user.mention}!\n\n"
        "🎥 I am a YouTube and M3U8 Downloader Bot.\n\n"
        "Available commands:\n"
        "/start - Start the bot\n"
        "/help - Show help message\n"
        "/ping - Check bot response\n"
        "/utube - Download from YouTube\n"
        "/m3u8 - Download M3U8 streams\n\n"  # Added M3U8 command to welcome message
        f"🕒 Bot Started: {START_TIME}\n"
        f"👨‍💻 Admin: @{ADMIN_USERNAME}"
    )

print(f"Bot Starting... Time: {START_TIME}")

if __name__ == "__main__":
    app.run()
