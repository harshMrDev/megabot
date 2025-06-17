import os
import asyncio
from pyrogram import Client
from pyrogram.types import BotCommand

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

app = Client(
    "youtube_downloader_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    plugins=dict(root="plugins")
)

async def set_commands():
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Show help"),
    ]
    await app.set_bot_commands(commands)

async def main():
    async with app:
        await set_commands()
        print("Bot is running. Type / in your bot chat to see the command menu!")
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
