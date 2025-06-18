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
START_TIME = "2025-06-18 14:37:16"

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

# Print startup message
print(f"Bot starting... Time: {START_TIME}")
logger.info(f"Bot initialization started by {ADMIN_USERNAME}")

# Environment variable check
required_vars = ['API_ID', 'API_HASH', 'BOT_TOKEN']
missing_vars = [var for var in required_vars if var not in os.environ]
if missing_vars:
    error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
    logger.error(error_msg)
    raise SystemExit(error_msg)

try:
    # Get environment variables
    api_id = int(os.environ["API_ID"])
    api_hash = os.environ["API_HASH"]
    bot_token = os.environ["BOT_TOKEN"]
except ValueError as e:
    logger.error(f"API_ID must be an integer, got: {os.environ.get('API_ID')}")
    raise SystemExit("Invalid API_ID")

# Initialize client
app = Client(
    "youtube_downloader_bot",
    api_id=api_id,
    api_hash=api_hash,
    bot_token=bot_token,
    plugins=dict(root="plugins"),
    in_memory=True,
    sleep_threshold=180  # Increased sleep threshold
)

class BotManager:
    def __init__(self):
        self.last_flood_wait = 0
        self.flood_wait_count = 0
        self.max_flood_waits = 3

    async def safe_api_call(self, func, *args, **kwargs):
        """Execute API calls with FloodWait handling"""
        try:
            await asyncio.sleep(2)  # Small delay before API call
            return await func(*args, **kwargs)
        except FloodWait as e:
            self.flood_wait_count += 1
            self.last_flood_wait = e.value
            logger.warning(f"FloodWait: {e.value} seconds (attempt {self.flood_wait_count})")
            
            if self.flood_wait_count >= self.max_flood_waits:
                logger.error("Too many FloodWait errors, restarting bot")
                return None
                
            if e.value > 1000:  # If wait is too long
                wait_time = 300  # Wait 5 minutes instead
                logger.info(f"Long FloodWait detected, waiting {wait_time} seconds instead")
            else:
                wait_time = e.value
                
            await asyncio.sleep(wait_time)
            return await self.safe_api_call(func, *args, **kwargs)
        except Exception as e:
            logger.error(f"API call error: {str(e)}")
            return None

    async def initialize_bot(self):
        """Initialize bot with FloodWait handling"""
        try:
            # Get bot info
            me = await self.safe_api_call(app.get_me)
            if not me:
                return False
                
            # Set commands
            commands = [
                BotCommand("start", "Start the bot"),
                BotCommand("help", "Show help message"),
                BotCommand("ping", "Check bot response"),
                BotCommand("utube", "Download from YouTube"),
                BotCommand("m3u8", "Download M3U8 streams")
            ]
            
            if not await self.safe_api_call(app.set_bot_commands, commands):
                logger.warning("Failed to set commands, continuing anyway")
            
            logger.info(f"Bot initialized as @{me.username}")
            return True
            
        except Exception as e:
            logger.error(f"Initialization error: {str(e)}")
            return False

    async def run(self):
        """Run the bot with proper error handling"""
        try:
            # Start the client
            await app.start()
            logger.info("Client started")
            
            # Initialize bot
            if not await self.initialize_bot():
                logger.error("Failed to initialize bot")
                return
            
            # Keep the bot running
            logger.info("Bot is ready")
            await idle()
            
        except FloodWait as e:
            logger.warning(f"Main FloodWait: {e.value} seconds")
            if e.value > 1000:
                logger.error("FloodWait too long, please wait and try again later")
                return
            await asyncio.sleep(e.value)
            await self.run()
            
        except Exception as e:
            logger.error(f"Runtime error: {str(e)}")
        
        finally:
            if app.is_connected:
                await app.stop()
                logger.info("Bot stopped")

def main():
    """Main entry point with retry mechanism"""
    bot_manager = BotManager()
    retry_count = 0
    max_retries = 3
    
    while retry_count < max_retries:
        try:
            logger.info(f"Starting bot (attempt {retry_count + 1}/{max_retries})")
            app.run(bot_manager.run())
            break
            
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            break
            
        except Exception as e:
            retry_count += 1
            logger.error(f"Error: {str(e)}")
            
            if retry_count < max_retries:
                wait_time = 60 * retry_count  # Increasing wait between retries
                logger.info(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                logger.error("Max retries reached")
                break
                
        finally:
            # Cleanup
            try:
                if os.path.exists('bot.log'):
                    with open('bot.log', 'a') as f:
                        f.write(f"\nBot stopped at {datetime.utcnow()}\n")
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

if __name__ == "__main__":
    main()
