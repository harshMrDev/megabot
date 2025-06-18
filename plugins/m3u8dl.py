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
START_TIME = "2025-06-18 13:50:08"

# Regular expression for M3U8 URLs
M3U8_REGEX = re.compile(
    r'https?://[^\s<>"]+?\.m3u8(?:\?[^\s<>"]*)?'
)

def extract_m3u8_links(text):
    """Extract M3U8 links from text"""
    return M3U8_REGEX.findall(text or "")

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
async def m3u8_command(client: Client, message: Message):
    """Handle /m3u8 command"""
    try:
        await message.reply_text(
            "📺 **M3U8 Stream Downloader**\n\n"
            "You can:\n"
            "1. Send an M3U8 URL directly\n"
            "2. Send a .txt file containing multiple M3U8 URLs\n\n"
            "Example URLs:\n"
            "▫️ https://example.com/stream.m3u8\n"
            "▫️ https://live.stream.com/index.m3u8\n\n"
            "Note: Maximum file size is 4GB per stream\n\n"
            f"Started at: {START_TIME}\n"
            f"Admin: @{ADMIN_USERNAME}",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error in m3u8 command: {e}")
        await message.reply_text("An error occurred. Please try again.")

@Client.on_message((filters.regex(M3U8_REGEX) | filters.document) & filters.private)
async def handle_m3u8_input(client: Client, message: Message):
    """Handle M3U8 URL or text file"""
    try:
        links = []
        
        # Handle text file
        if message.document and message.document.mime_type == "text/plain":
            file = await client.download_media(message.document)
            try:
                with open(file, "r") as f:
                    for line in f:
                        links.extend(extract_m3u8_links(line.strip()))
                os.remove(file)
                logger.info(f"Processed text file with {len(links)} M3U8 links")
            except Exception as e:
                logger.error(f"Error processing text file: {e}")
                await message.reply_text("❌ Error processing text file. Make sure it contains valid M3U8 URLs.")
                return
        # Handle direct URL
        elif message.text:
            links = extract_m3u8_links(message.text)
            logger.info(f"Extracted {len(links)} M3U8 links from text")

        if not links:
            await message.reply_text("❌ No valid M3U8 URLs found.")
            return

        total_links = len(links)
        logger.info(f"Processing {total_links} M3U8 links")

        # Process each link
        for index, link in enumerate(links, 1):
            try:
                # Send initial message
                progress_msg = await message.reply_text(
                    f"🎯 Processing link {index}/{total_links}:\n`{link}`",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Generate output filename
                output_file = f"/tmp/stream_{message.from_user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ts"
                
                # Download the stream
                await download_m3u8(link, output_file)
                
                # Check file size
                size = os.path.getsize(output_file)
                if size == 0:
                    await progress_msg.edit_text("❌ Download failed: Empty file")
                    os.remove(output_file)
                    continue
                    
                if size > 4 * 1024 * 1024 * 1024:  # 4GB limit
                    await progress_msg.edit_text("❌ File too large! Max 4GB allowed.")
                    os.remove(output_file)
                    continue
                
                # Upload to Telegram
                await progress_msg.edit_text("✅ Uploading to Telegram...")
                await message.reply_document(
                    output_file,
                    caption=f"📺 Stream {index}/{total_links} downloaded from:\n`{link}`",
                    parse_mode=ParseMode.MARKDOWN
                )
                
            except Exception as e:
                await progress_msg.edit_text(
                    f"❌ Download failed for link {index}/{total_links}:\n`{str(e)}`",
                    parse_mode=ParseMode.MARKDOWN
                )
            
            finally:
                # Cleanup
                try:
                    os.remove(output_file)
                    logger.info(f"Cleaned up temporary file for link {index}/{total_links}")
                except:
                    pass

    except Exception as e:
        logger.error(f"Error handling M3U8 input: {e}")
        await message.reply_text("❌ An error occurred. Please try again.")

logger.info(f"M3U8 downloader plugin loaded. Started at {START_TIME}")
