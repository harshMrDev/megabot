import os
import sys
import logging
import asyncio
from pyrogram import Client, idle
from pyrogram.types import BotCommand
from pyrogram.errors import ApiIdInvalid, AccessTokenInvalid, AuthKeyUnregistered

# Set up logging to both file and console
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
print("Bot starting...")
logger.info("Bot initialization started")

# Environment variable check with detailed logging
required_vars = ['API_ID', 'API_HASH', 'BOT_TOKEN']
missing_vars = [var for var in required_vars if var not in os.environ]
if missing_vars:
    error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
    logger.error(error_msg)
    raise SystemExit(error_msg)

try:
    # Log the values (but mask them for security)
    api_id = int(os.environ["API_ID"])
    api_hash = os.environ["API_HASH"]
    bot_token = os.environ["BOT_TOKEN"]
    
    logger.info(f"API_ID: {'*' * len(str(api_id))}")
    logger.info(f"API_HASH: {api_hash[:4]}...{api_hash[-4:]}")
    logger.info(f"BOT_TOKEN: {bot_token[:4]}...{bot_token[-4:]}")
    
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
        await app.get_me()
        logger.info("Bot token is valid")
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
            BotCommand("help", "Show help"),
        ]
        await app.set_bot_commands(commands)
        logger.info("Bot commands set successfully")
    except Exception as e:
        logger.error(f"Failed to set bot commands: {str(e)}")
        # Don't raise here, as this is not critical

async def main():
    try:
        logger.info("Starting bot...")
        
        # Start the client
        await app.start()
        logger.info("Client started successfully")
        
        # Check token validity
        if not await check_token_validity():
            logger.error("Token validation failed")
            return
        
        # Set commands
        await set_commands()
        
        # Log successful startup
        logger.info("Bot is fully initialized and running")
        me = await app.get_me()
        logger.info(f"Bot Username: @{me.username}")
        
        # Keep the bot running
        logger.info("Bot is now listening for updates")
        await idle()
        
    except Exception as e:
        logger.error(f"Critical error in main: {str(e)}")
        raise
    finally:
        logger.info("Stopping bot...")
        await app.stop()

if __name__ == "__main__":
    try:
        logger.info("Starting bot process")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        raise
    finally:
        logger.info("Bot process finished")
