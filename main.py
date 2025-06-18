import os
import logging
import asyncio
from pyrogram import Client
from pyrogram.types import BotCommand

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get environment variables with error checking
try:
    API_ID = int(os.environ["API_ID"])
    API_HASH = os.environ["API_HASH"]
    BOT_TOKEN = os.environ["BOT_TOKEN"]
except KeyError as e:
    logger.error(f"Missing environment variable: {e}")
    raise
except ValueError as e:
    logger.error(f"Invalid API_ID value: {e}")
    raise

app = Client(
    "youtube_downloader_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    plugins=dict(root="plugins")
)

async def set_commands():
    try:
        commands = [
            BotCommand("start", "Start the bot"),
            BotCommand("help", "Show help"),
        ]
        await app.set_bot_commands(commands)
        logger.info("Bot commands set successfully")
    except Exception as e:
        logger.error(f"Failed to set bot commands: {e}")
        raise

async def main():
    try:
        logger.info("Starting bot...")
        async with app:
            await set_commands()
            logger.info("Bot is running. Type / in your bot chat to see the command menu!")
            # Keep the bot running
            await asyncio.Event().wait()
    except Exception as e:
        logger.error(f"Bot crashed with error: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        logger.info("Initializing bot...")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        raise
