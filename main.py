import os
import sys
import logging
import asyncio
from datetime import datetime
from pyrogram import Client, idle
from pyrogram.types import BotCommand
from pyrogram.errors import ApiIdInvalid, AccessTokenInvalid, AuthKeyUnregistered, FloodWait

# Constants
ADMIN_USERNAME = "harshMrDev"
START_TIME = "2025-06-18 14:29:35"

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

# Environment variable check with detailed logging
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

# Initialize the client with explicit error handling
app = Client(
    "youtube_downloader_bot",
    api_id=api_id,
    api_hash=api_hash,
    bot_token=bot_token,
    plugins=dict(root="plugins"),
    in_memory=True,
    sleep_threshold=60  # Increase sleep threshold
)

async def check_token_validity():
    """Check if the bot token is valid by making a simple API call"""
    try:
        await asyncio.sleep(2)  # Add delay before check
        me = await app.get_me()
        logger.info(f"Bot token is valid for @{me.username}")
        return True
    except FloodWait as e:
        logger.warning(f"FloodWait in token check: {e.value} seconds")
        await asyncio.sleep(e.value)
        return await check_token_validity()
    except Exception as e:
        logger.error(f"Error checking token: {str(e)}")
        return False

async def set_commands():
    """Set bot commands with error handling"""
    try:
        await asyncio.sleep(3)  # Add delay before setting commands
        commands = [
            BotCommand("start", "Start the bot"),
            BotCommand("help", "Show help message"),
            BotCommand("ping", "Check bot response"),
            BotCommand("utube", "Download from YouTube"),
            BotCommand("m3u8", "Download M3U8 streams")
        ]
        await app.set_bot_commands(commands)
        logger.info("Bot commands set successfully")
    except FloodWait as e:
        logger.warning(f"FloodWait in set_commands: {e.value} seconds")
        await asyncio.sleep(e.value)
        return await set_commands()
    except Exception as e:
        logger.error(f"Failed to set commands: {e}")

async def initialize_bot():
    """Initialize bot settings and configurations"""
    try:
        # Add initial delay
        await asyncio.sleep(5)
        
        # Check token validity
        if not await check_token_validity():
            logger.error("Token validation failed")
            return False
        
        # Add delay between operations
        await asyncio.sleep(3)
        
        # Set commands
        await set_commands()
        
        # Log successful initialization
        logger.info("Bot initialization completed successfully")
        return True
        
    except FloodWait as e:
        logger.warning(f"FloodWait in initialize_bot: {e.value} seconds")
        await asyncio.sleep(e.value)
        return await initialize_bot()
    except Exception as e:
        logger.error(f"Error during initialization: {e}")
        return False

async def main():
    """Main bot execution function"""
    try:
        logger.info(f"Starting bot at {START_TIME}")
        
        # Start with delay
        await asyncio.sleep(2)
        
        # Start the client
        await app.start()
        logger.info("Client started successfully")
        
        # Initialize with delay
        await asyncio.sleep(3)
        if not await initialize_bot():
            logger.error("Bot initialization failed")
            return
        
        # Log successful startup
        me = await app.get_me()
        logger.info(f"Bot is running as @{me.username}")
        
        # Keep the bot running
        await idle()
        
    except FloodWait as e:
        logger.warning(f"FloodWait in main: {e.value} seconds")
        if e.value > 1000:  # If wait is too long
            logger.error(f"FloodWait too long ({e.value}s), restarting in 5 minutes")
            await asyncio.sleep(300)  # Wait 5 minutes
            return await main()
        await asyncio.sleep(e.value)
        return await main()
    except Exception as e:
        logger.error(f"Critical error: {str(e)}")
        raise
    finally:
        if app.is_connected:
            await app.stop()

def run_bot():
    """Run the bot with retry mechanism"""
    retries = 0
    max_retries = 3
    
    while retries < max_retries:
        try:
            logger.info(f"Starting bot (attempt {retries + 1}/{max_retries})")
            app.run(main())
            break
        except FloodWait as e:
            retries += 1
            wait_time = min(e.value, 300)  # Cap wait time at 5 minutes
            logger.warning(f"FloodWait: waiting {wait_time}s before retry {retries}/{max_retries}")
            time.sleep(wait_time)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            break
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            retries += 1
            if retries < max_retries:
                time.sleep(5)
        finally:
            try:
                if os.path.exists('bot.log'):
                    with open('bot.log', 'a') as f:
                        f.write(f"\nBot stopped at {datetime.utcnow()}\n")
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

if __name__ == "__main__":
    run_bot()
