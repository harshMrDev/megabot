import os
import sys
import time
import logging
import asyncio
from datetime import datetime
from pyrogram import Client, idle
from pyrogram.types import BotCommand
from pyrogram.errors import ApiIdInvalid, AccessTokenInvalid, AuthKeyUnregistered, FloodWait

# Constants
ADMIN_USERNAME = "harshMrDev"
START_TIME = "2025-06-18 13:50:08"

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

# Environment variables check
required_vars = ['API_ID', 'API_HASH', 'BOT_TOKEN']
missing_vars = [var for var in required_vars if var not in os.environ]
if missing_vars:
    error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
    logger.error(error_msg)
    raise SystemExit(error_msg)

# Get environment variables
try:
    API_ID = int(os.environ["API_ID"])
    API_HASH = os.environ["API_HASH"]
    BOT_TOKEN = os.environ["BOT_TOKEN"]
except ValueError as e:
    logger.error(f"API_ID must be an integer, got: {os.environ.get('API_ID')}")
    raise SystemExit("Invalid API_ID")

# Initialize the client
app = Client(
    name="youtube_downloader_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    plugins=dict(root="plugins"),
    in_memory=True,
    workers=6
)

# Define bot commands
COMMANDS = [
    BotCommand("start", "Start the bot"),
    BotCommand("help", "Show help message"),
    BotCommand("ping", "Check bot response"),
    BotCommand("utube", "Download from YouTube"),
    BotCommand("m3u8", "Download M3U8 streams")
]

async def setup_commands():
    """Set up bot commands"""
    try:
        await app.set_bot_commands(COMMANDS)
        logger.info("Bot commands set successfully")
    except FloodWait as e:
        logger.warning(f"FloodWait: waiting {e.value} seconds")
        await asyncio.sleep(e.value)
        await setup_commands()
    except Exception as e:
        logger.error(f"Failed to set commands: {e}")

async def start():
    """Start the bot"""
    global start_time
    
    try:
        # Start the client
        await app.start()
        logger.info("Client started successfully")
        
        # Set up commands
        await setup_commands()
        
        # Get bot info
        me = await app.get_me()
        logger.info(f"Bot started as @{me.username}")
        
        # Keep running
        await idle()
        
    except FloodWait as e:
        logger.warning(f"FloodWait: waiting {e.value} seconds")
        await asyncio.sleep(e.value)
        await start()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise
    finally:
        await app.stop()

def main():
    """Main function"""
    try:
        logger.info(f"Starting bot... Time: {START_TIME}")
        app.run(start())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        logger.info("Bot stopped")

if __name__ == "__main__":
    main()
