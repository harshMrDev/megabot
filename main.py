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
START_TIME = "2025-06-18 14:03:27"

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

# Define bot commands
COMMANDS = [
    BotCommand("start", "Start the bot"),
    BotCommand("help", "Show help message"),
    BotCommand("ping", "Check bot response"),
    BotCommand("utube", "Download from YouTube"),
    BotCommand("m3u8", "Download M3U8 streams")
]

class Bot:
    def __init__(self):
        self.app = None
        self.retry_count = 0
        self.max_retries = 3
        self.is_running = False

    def create_client(self):
        """Create a new client instance"""
        return Client(
            name="youtube_downloader_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins=dict(root="plugins"),
            in_memory=True,
            workers=4,
            max_concurrent_transmissions=1
        )

    async def setup_commands(self):
        """Set up bot commands with retry logic"""
        retry = 0
        while retry < 3:
            try:
                await self.app.set_bot_commands(COMMANDS)
                logger.info("Bot commands set successfully")
                return True
            except FloodWait as e:
                if e.value > 300:  # If wait is more than 5 minutes
                    logger.warning(f"Long FloodWait in setup_commands: {e.value}s")
                    return False
                logger.info(f"FloodWait in setup_commands: waiting {e.value}s")
                await asyncio.sleep(e.value)
                retry += 1
            except Exception as e:
                logger.error(f"Error setting commands: {e}")
                return False
        return False

    async def start_bot(self):
        """Start the bot with proper error handling"""
        try:
            self.is_running = True
            self.app = self.create_client()
            
            # Start the client
            await self.app.start()
            logger.info("Client started successfully")
            
            # Initial delay
            await asyncio.sleep(2)
            
            # Setup commands
            if not await self.setup_commands():
                logger.warning("Failed to set commands, continuing anyway")
            
            # Get bot info
            me = await self.app.get_me()
            logger.info(f"Bot started as @{me.username}")
            
            # Keep the bot running
            await idle()
            
        except FloodWait as e:
            logger.warning(f"FloodWait in start_bot: {e.value}s")
            if e.value > 300:  # If wait is more than 5 minutes
                raise
            await asyncio.sleep(e.value)
            return await self.start_bot()
            
        except Exception as e:
            logger.error(f"Error in start_bot: {e}")
            raise
        
        finally:
            self.is_running = False
            if self.app:
                await self.app.stop()

    async def run(self):
        """Run the bot with retry mechanism"""
        while self.retry_count < self.max_retries:
            try:
                await self.start_bot()
                break
            
            except FloodWait as e:
                self.retry_count += 1
                if e.value > 300:  # If wait is more than 5 minutes
                    logger.error(f"FloodWait too long ({e.value}s), retrying in 5 minutes")
                    await asyncio.sleep(300)  # Wait 5 minutes before retry
                else:
                    logger.warning(f"FloodWait: waiting {e.value}s before retry {self.retry_count}/{self.max_retries}")
                    await asyncio.sleep(e.value)
            
            except Exception as e:
                self.retry_count += 1
                logger.error(f"Error: {str(e)}")
                if self.retry_count < self.max_retries:
                    await asyncio.sleep(5)
                else:
                    logger.error("Max retries reached, stopping bot")
                    break
            
            finally:
                if self.app and self.app.is_connected:
                    await self.app.stop()
                await asyncio.sleep(1)  # Small delay between retries

def main():
    """Main entry point"""
    bot = Bot()
    try:
        logger.info(f"Starting bot... Time: {START_TIME}")
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        logger.info("Bot process finished")

if __name__ == "__main__":
    main()
