import os
import sys
import time
import logging
import asyncio
from datetime import datetime
from pyrogram import Client, idle
from pyrogram.types import BotCommand
from pyrogram.errors import FloodWait

# Constants
ADMIN_USERNAME = "harshMrDev"
START_TIME = "2025-06-18 14:40:43"

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Check environment variables
if not all([os.getenv('API_ID'), os.getenv('API_HASH'), os.getenv('BOT_TOKEN')]):
    logger.error("Missing environment variables!")
    sys.exit(1)

# Initialize bot
app = Client(
    "youtube_downloader_bot",
    api_id=os.getenv('API_ID'),
    api_hash=os.getenv('API_HASH'),
    bot_token=os.getenv('BOT_TOKEN'),
    plugins=dict(root="plugins"),
    sleep_threshold=60
)

async def start():
    """Start the bot"""
    try:
        await app.start()
        logger.info("Bot started!")

        # Set commands
        commands = [
            BotCommand("start", "Start the bot"),
            BotCommand("help", "Show help message"),
            BotCommand("ping", "Check bot response"),
            BotCommand("utube", "Download from YouTube"),
            BotCommand("m3u8", "Download M3U8 streams")
        ]
        
        await app.set_bot_commands(commands)
        logger.info("Commands set!")

        # Keep alive
        await idle()

    except FloodWait as e:
        logger.warning(f"FloodWait: {e.value} seconds")
        if e.value > 300:  # If wait is more than 5 minutes
            logger.error("Long FloodWait detected, exiting...")
            return
        await asyncio.sleep(e.value)
        return await start()

    except Exception as e:
        logger.error(f"Error: {str(e)}")

    finally:
        await app.stop()

def main():
    """Main function"""
    try:
        logger.info(f"Starting bot process... Time: {START_TIME}")
        app.run(start())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
    finally:
        if os.path.exists('bot.log'):
            with open('bot.log', 'a') as f:
                f.write(f"\nBot stopped at {datetime.now()}\n")

if __name__ == "__main__":
    main()
