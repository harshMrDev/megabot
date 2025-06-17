import os
import asyncio
from pyrogram import Client
from pyrogram.types import BotCommand

# Get credentials from Railway environment variables
api_id = int(os.environ["API_ID"])
api_hash = os.environ["API_HASH"]
bot_token = os.environ["BOT_TOKEN"]

# Plugins directory (where your utube.py lives)
app = Client(
    "mybot",
    api_id=api_id,
    api_hash=api_hash,
    bot_token=bot_token,
    plugins=dict(root="plugins")
)

async def set_commands():
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("utube", "Download from YouTube"),
        BotCommand("help", "Show help"),
        # Add more commands if you add more features/plugins
    ]
    await app.set_bot_commands(commands)

if __name__ == "__main__":
    app.start()
    asyncio.get_event_loop().run_until_complete(set_commands())
    print("Bot is running. Type / in your bot chat to see command menu!")
    app.idle()
