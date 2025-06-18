import os
import logging
from datetime import datetime
from pyrogram import Client, idle
from pyrogram.types import BotCommand
from pyrogram.errors import FloodWait

# Constants
START_TIME = "2025-06-18 14:43:36"
ADMIN_USERNAME = "harshMrDev"

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Init bot
app = Client(
    "youtube_downloader_bot",
    api_id=os.environ.get("API_ID"),
    api_hash=os.environ.get("API_HASH"),
    bot_token=os.environ.get("BOT_TOKEN"),
    plugins=dict(root="plugins")
)

# Commands
COMMANDS = [
    BotCommand("start", "Start the bot"),
    BotCommand("help", "Show help message"), 
    BotCommand("ping", "Check bot response"),
    BotCommand("utube", "Download from YouTube"),
    BotCommand("m3u8", "Download M3U8 streams")
]

async def main():
    """Start bot"""
    async with app:
        try:
            await app.set_bot_commands(COMMANDS)
            await idle()
        except FloodWait as e:
            logger.warning(f"FloodWait: {e.value} seconds")
            if e.value > 60:
                logger.error("Long FloodWait, exiting...")
                return
            await asyncio.sleep(e.value)
            return await main()
        except Exception as e:
            logger.error(f"Error: {str(e)}")

if __name__ == "__main__":
    app.run(main())
