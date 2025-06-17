from pyrogram import Client, filters
from pyrogram.types import Message

@Client.on_message(filters.document & filters.private)
async def utube_txt_handler(client, message: Message):
    doc = message.document
    # Check for text/plain or .txt file
    if (doc.mime_type == "text/plain") or (doc.file_name and doc.file_name.lower().endswith(".txt")):
        file_path = await message.download()
        links = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    link = line.strip()
                    if link:
                        links.append(link)
            if links:
                await message.reply(f"Found {len(links)} links:\n" + "\n".join(links))
            else:
                await message.reply("No links found in the file.")
        except Exception as e:
            await message.reply(f"Error reading file: {e}")
    else:
        await message.reply("Please send a valid .txt file containing links.")
