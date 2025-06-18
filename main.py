import os
import sys
import logging
import asyncio
from datetime import datetime
from pyrogram import Client, idle
from pyrogram.types import BotCommand
from pyrogram.errors import ApiIdInvalid, AccessTokenInvalid, AuthKeyUnregistered

# Constants
ADMIN_USERNAME = "harshMrDev"
START_TIME = "2025-06-18 12:40:28"

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
    
    # Log the values (but mask them for security)
    logger.info(f"API_ID: {'*' * len(str(api_id))}")
    logger.info(f"API_HASH: {api_hash[:4]}...{api_hash[-4:]}")
    logger.info(f"BOT_TOKEN: {bot_token[:4]}...{bot_token[-4:]}")
    logger.info(f"Admin Username: @{ADMIN_USERNAME}")
    
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
    in_memory=True  # Don't save session files
)

async def check_token_validity():
    """Check if the bot token is valid by making a simple API call"""
    try:
        me = await app.get_me()
        logger.info(f"Bot token is valid for @{me.username}")
        return True
    except ApiIdInvalid:
        logger.error("API ID/Hash are invalid")
        return False
    except AccessTokenInvalid:
        logger.error("Bot token is invalid")
        return False
    except AuthKeyUnregistered:
        logger.error("Bot token is unregistered")
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking bot token: {str(e)}")
        return False

async def set_commands():
    """Set bot commands with error handling"""
    try:
        commands = [
            BotCommand("start", "Start the bot"),
            BotCommand("help", "Show help message"),
            BotCommand("ping", "Check bot response"),
            BotCommand("utube", "Download from YouTube")
        ]
        await app.set_bot_commands(commands)
        logger.info("Bot commands set successfully")
    except Exception as e:
        logger.error(f"Failed to set bot commands: {e}")

async def initialize_bot():
    """Initialize bot settings and configurations"""
    try:
        # Check token validity
        if not await check_token_validity():
            logger.error("Token validation failed")
            return False
        
        # Set commands
        await set_commands()
        
        # Log successful initialization
        logger.info("Bot initialization completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error during bot initialization: {e}")
        return False

async def main():
    """Main bot execution function"""
    try:
        logger.info(f"Starting bot at {START_TIME}")
        
        # Start the client using context manager
        async with app:
            # Initialize bot
            if not await initialize_bot():
                logger.error("Bot initialization failed")
                return
            
            # Log successful startup
            me = await app.get_me()
            logger.info(f"Bot is running as @{me.username}")
            logger.info("Bot is now listening for updates")
            
            # Keep the bot running
            await idle()
            
    except Exception as e:
        logger.error(f"Critical error in main: {str(e)}")
        raise
    finally:
        logger.info("Stopping bot...")
        if app.is_connected:
            await app.stop()
            logger.info("Bot stopped successfully")

def cleanup():
    """Cleanup function to handle bot shutdown"""
    try:
        # Remove any temporary files or cleanup tasks here
        if os.path.exists('bot.log'):
            with open('bot.log', 'a') as f:
                f.write(f"\nBot stopped at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}\n")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

def run_bot():
    """Run the bot with proper event loop and error handling"""
    try:
        logger.info(f"Starting bot process as {ADMIN_USERNAME}")
        app.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        raise
    finally:
        cleanup()
        logger.info("Bot process finished")

if __name__ == "__main__":
    run_bot()
