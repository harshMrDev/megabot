import os
import re
import logging
import asyncio
import aiohttp
import m3u8
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
ADMIN_USERNAME = "harshMrDev"
START_TIME = "2025-06-18 13:01:35"

# Regular expression for M3U8 URLs
M3U8_REGEX = re.compile(
    r'https?://[^\s<>"]+?\.m3u8(?:\?[^\s<>"]*)?'
)

def make_progress_bar(current, total, bar_length=18):
    if total == 0:
        return "🟡 Starting..."
    percent = current / total
    filled_len = int(bar_length * percent)
    bar = "🟩" * filled_len + "⬜" * (bar_length - filled_len)
    percent_text = f"{percent*100:5.1f}%"
    return f"{bar} `{percent_text}`"

async def download_m3u8(url, output_path):
    """Download M3U8 stream and combine segments"""
    try:
        # Parse M3U8 playlist
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                m3u8_text = await response.text()
                playlist = m3u8.loads(m3u8_text)

        if not playlist.segments:
            raise Exception("No segments found in playlist")

        # Get base URL for relative paths
        base_url = url.rsplit('/', 1)[0] + '/'

        # Create temporary directory for segments
        temp_dir = f"/tmp/m3u8_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(temp_dir, exist_ok=True)

        # Download all segments
        segment_files = []
        total_segments = len(playlist.segments)

        async def download_segment(session, segment, index):
            segment_url = segment.uri
            if not segment_url.startswith('http'):
                segment_url = base_url + segment_url

            segment_path = f"{temp_dir}/segment_{index:05d}.ts"
            async with session.get(segment_url) as response:
                if response.status == 200:
                    with open(segment_path, 'wb') as f:
                        f.write(await response.read())
                    return segment_path
                return None

        async with aiohttp.ClientSession() as session:
            tasks = []
            for i, segment in enumerate(playlist.segments):
                task = asyncio.create_task(download_segment(session, segment, i))
                tasks.append(task)

            segment_files = await asyncio.gather(*tasks)
            segment_files = [f for f in segment_files if f]

        # Combine segments
        with open(output_path, 'wb') as outfile:
            for segment_file in segment_files:
                if os.path.exists(segment_file):
                    with open(segment_file, 'rb') as infile:
                        outfile.write(infile.read())
                    os.remove(segment_file)

        # Cleanup
        try:
            os.rmdir(temp_dir)
        except:
            pass

        return True

    except Exception as e:
        logger.error(f"Error downloading M3U8: {str(e)}")
        raise

@Client.on_message(filters.command(["m3u8"]) & filters.private)
async def m3u8_command(client, message: Message):
    """Handle /m3u8 command"""
    try:
        await message.reply_text(
            "📺 **M3U8 Stream Downloader**\n\n"
            "Send me an M3U8 URL to download the stream.\n\n"
            "Example URLs:\n"
            "▫️ https://example.com/stream.m3u8\n"
            "▫️ https://live.stream.com/index.m3u8\n\n"
            "Note: Maximum file size is 4GB",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error in m3u8 command: {e}")
        await message.reply_text("An error occurred. Please try again.")

@Client.on_message(filters.regex(M3U8_REGEX) & filters.private)
async def handle_m3u8_link(client, message: Message):
    """Handle M3U8 URL"""
    try:
        # Extract M3U8 URL
        url = M3U8_REGEX.findall(message.text)[0]
        
        # Send initial message
        progress_msg = await message.reply_text("🎯 Processing M3U8 stream...")
        
        # Generate output filename
        output_file = f"/tmp/stream_{message.from_user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ts"
        
        try:
            # Download the stream
            await download_m3u8(url, output_file)
            
            # Check file size
            size = os.path.getsize(output_file)
            if size == 0:
                await progress_msg.edit_text("❌ Download failed: Empty file")
                os.remove(output_file)
                return
                
            if size > 4 * 1024 * 1024 * 1024:  # 4GB limit
                await progress_msg.edit_text("❌ File too large! Max 4GB allowed.")
                os.remove(output_file)
                return
            
            # Upload to Telegram
            await progress_msg.edit_text("✅ Uploading to Telegram...")
            await message.reply_document(
                output_file,
                caption=f"📺 Stream downloaded from:\n`{url}`",
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            await progress_msg.edit_text(f"❌ Download failed:\n`{str(e)}`", parse_mode=ParseMode.MARKDOWN)
        
        finally:
            # Cleanup
            try:
                os.remove(output_file)
            except:
                pass
            
    except Exception as e:
        logger.error(f"Error handling M3U8 link: {e}")
        await message.reply_text("❌ An error occurred. Please try again.")

# Update the help command in utube.py to include M3U8 functionality
@Client.on_message(filters.command(["help"]) & filters.private)
async def help_command(client, message: Message):
    """Updated help command including M3U8"""
    try:
        await message.reply_text(
            "📖 **Help Menu**\n\n"
            "Available commands:\n"
            "/start - Start the bot\n"
            "/help - Show this help message\n"
            "/ping - Check bot response\n"
            "/utube - Download from YouTube\n"
            "/m3u8 - Download M3U8 streams\n\n"
            "Features:\n"
            "1. YouTube Downloader:\n"
            "   • Send YouTube links\n"
            "   • Choose Audio/Video\n"
            "   • Multiple quality options\n\n"
            "2. M3U8 Downloader:\n"
            "   • Send M3U8 stream URL\n"
            "   • Downloads and combines segments\n"
            "   • Supports live streams\n\n"
            "Note: Maximum file size is 4GB\n\n"
            f"Bot Started: {START_TIME}\n"
            f"Admin: @{ADMIN_USERNAME}",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error in help command: {e}")
        await message.reply_text("An error occurred. Please try again.")
