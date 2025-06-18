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
START_TIME = "2025-06-18 13:56:32"

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
    workers=6,
    max_concurrent_transmissions=2  # Limit concurrent operations
)

# Define bot commands
COMMANDS = [
    BotCommand("start", "Start the bot"),
    BotCommand("help", "Show help message"),
    BotCommand("ping", "Check bot response"),
    BotCommand("utube", "Download from YouTube"),
    BotCommand("m3u8", "Download M3U8 streams")
]

async def handle_flood_wait(action, *args, **kwargs):
    """Handle FloodWait with exponential backoff"""
    retries = 0
    max_retries = 3
    base_delay = 5

    while retries < max_retries:
        try:
            return await action(*args, **kwargs)
        except FloodWait as e:
            wait_time = e.value
            logger.warning(f"FloodWait: Need to wait {wait_time} seconds")
            
            if wait_time > 1800:  # If wait time > 30 minutes
                logger.error(f"FloodWait too long ({wait_time}s), stopping bot")
                raise
            
            await asyncio.sleep(wait_time)
            retries += 1
        except Exception as e:
            logger.error(f"Error during {action.__name__}: {str(e)}")
            raise

    raise Exception(f"Max retries ({max_retries}) exceeded")

async def setup_commands():
    """Set up bot commands"""
    try:
        await handle_flood_wait(app.set_bot_commands, COMMANDS)
        logger.info("Bot commands set successfully")
    except Exception as e:
        logger.error(f"Failed to set commands: {e}")

async def start():
    """Start the bot"""
    try:
        # Start with delay to avoid flood
        await asyncio.sleep(2)
        
        # Start the client
        await app.start()
        logger.info("Client started successfully")
        
        # Add delay before setting commands
        await asyncio.sleep(3)
        
        # Set up commands
        await setup_commands()
        
        # Get bot info
        me = await handle_flood_wait(app.get_me)
        logger.info(f"Bot started as @{me.username}")
        
        # Keep running
        await idle()
        
    except FloodWait as e:
        if e.value > 1800:  # If wait time > 30 minutes
            logger.error(f"FloodWait too long ({e.value}s), stopping bot")
            raise
        logger.warning(f"FloodWait: waiting {e.value} seconds")
        await asyncio.sleep(e.value)
        return await start()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise
    finally:
        await app.stop()

def main():
    """Main function"""
    retry_count = 0
    max_retries = 3
    
    while retry_count < max_retries:
        try:
            logger.info(f"Starting bot... Time: {START_TIME}")
            app.run(start())
            break
        except FloodWait as e:
            retry_count += 1
            if e.value > 1800:  # If wait time > 30 minutes
                logger.error(f"FloodWait too long ({e.value}s), stopping bot")
                break
            logger.warning(f"FloodWait: Waiting {e.value}s before retry {retry_count}/{max_retries}")
            time.sleep(e.value)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            break
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            retry_count += 1
            if retry_count < max_retries:
                time.sleep(10)
            else:
                raise
        finally:
            logger.info("Bot stopped")

if __name__ == "__main__":
    main()
