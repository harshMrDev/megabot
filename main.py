import os
import asyncio
from pyrogram import Client
from pyrogram.types import BotCommand

# Get environment variables (set these in Railway's Variables tab)
api_id = int(os.environ["API_ID"])
api_hash = os.environ["API_HASH"]
bot_token = os.environ["BOT_TOKEN"]

# Initialize the Pyrogram Client with plugins directory
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
        # Add more commands here if needed
    ]
    await app.set_bot_commands(commands)

async def main():
    async with app:
        await set_commands()
        print("Bot is running. Type / in your bot chat to see the command menu!")
        await asyncio.Event().wait()  # Keeps the bot running

if __name__ == "__main__":
    asyncio.run(main())
