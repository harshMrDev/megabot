import os
import re
import m3u8
import aiohttp
import asyncio
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message

# Constants
START_TIME = "2025-06-18 15:56:56"
ADMIN_USERNAME = "harshMrDev"
CHUNK_SIZE = 1024*1024  # 1MB chunks
MAX_RETRIES = 3
TIMEOUT = 30  # 30 seconds timeout

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# M3U8 URL pattern
M3U8_REGEX = r'https?://[^\s<>"]+?\.m3u8(?:\?[^\s<>"]*)?'

async def download_m3u8_stream(url: str, output_file: str, status_msg: Message) -> bool:
    """Download M3U8 stream with progress updates"""
    try:
        async with aiohttp.ClientSession() as session:
            # Get M3U8 playlist
            async with session.get(url, timeout=TIMEOUT) as response:
                if response.status != 200:
                    logger.error(f"Failed to get playlist: {response.status}")
                    return False
                
                m3u8_text = await response.text()
                playlist = m3u8.loads(m3u8_text)

                if not playlist.segments:
                    logger.error("No segments found in playlist")
                    await status_msg.edit_text("❌ Error: No segments found in playlist")
                    return False

                # Get base URL for relative paths
                base_url = url.rsplit('/', 1)[0] + '/'
                total_segments = len(playlist.segments)
                
                await status_msg.edit_text(
                    f"📥 Found {total_segments} segments\n"
                    "⏳ Starting download..."
                )

                # Download segments
                async with aiofiles.open(output_file, 'wb') as outfile:
                    for idx, segment in enumerate(playlist.segments, 1):
                        segment_url = segment.uri
                        if not segment_url.startswith('http'):
                            segment_url = base_url + segment_url

                        # Retry logic for segment download
                        for retry in range(MAX_RETRIES):
                            try:
                                async with session.get(segment_url, timeout=TIMEOUT) as seg_response:
                                    if seg_response.status == 200:
                                        data = await seg_response.read()
                                        await outfile.write(data)
                                        break
                                    else:
                                        if retry == MAX_RETRIES - 1:
                                            logger.error(f"Failed to download segment {idx}: {seg_response.status}")
                                            return False
                                        await asyncio.sleep(1)
                            except Exception as e:
                                if retry == MAX_RETRIES - 1:
                                    logger.error(f"Error downloading segment {idx}: {str(e)}")
                                    return False
                                await asyncio.sleep(1)

                        # Update progress every 5 segments
                        if idx % 5 == 0 or idx == total_segments:
                            progress = idx * 100 / total_segments
                            await status_msg.edit_text(
                                f"📥 Downloading: {progress:.1f}%\n"
                                f"Segments: {idx}/{total_segments}"
                            )

                return True

    except Exception as e:
        logger.error(f"M3U8 download error: {str(e)}")
        await status_msg.edit_text(f"❌ Download failed: {str(e)}")
        return False

@Client.on_message(filters.command("m3u8"))
async def m3u8_command(client: Client, message: Message):
    """Handle /m3u8 command"""
    await message.reply_text(
        "📥 **M3U8 Stream Downloader**\n\n"
        "Send me:\n"
        "• Direct M3U8 URL or\n"
        "• Text file with M3U8 URLs\n\n"
        "I will download and send the videos to you!"
    )

@Client.on_message((filters.regex(M3U8_REGEX) | filters.document) & filters.private)
async def handle_m3u8(client: Client, message: Message):
    """Handle M3U8 URLs or text files containing M3U8 URLs"""
    try:
        links = []
        
        # Handle text file
        if message.document and message.document.mime_type == "text/plain":
            status = await message.reply_text("📄 Reading file...")
            file = await message.download()
            with open(file, 'r') as f:
                content = f.read()
                links.extend(re.findall(M3U8_REGEX, content))
            os.remove(file)
            
        # Handle direct URL
        elif message.text:
            links.extend(re.findall(M3U8_REGEX, message.text))
            
        if not links:
            await message.reply_text(
                "❌ No valid M3U8 URLs found.\n\n"
                "Please send:\n"
                "• Direct M3U8 URL or\n"
                "• Text file with M3U8 URLs"
            )
            return

        status_msg = await message.reply_text(
            f"🔍 Found {len(links)} M3U8 URL(s)\n"
            "⏳ Processing..."
        )

        for idx, url in enumerate(links, 1):
            try:
                await status_msg.edit_text(
                    f"📥 Processing stream {idx}/{len(links)}\n"
                    f"URL: `{url}`"
                )

                # Create output filename
                output_file = f"stream_{message.from_user.id}_{int(datetime.now().timestamp())}.ts"
                
                # Download stream
                success = await download_m3u8_stream(url, output_file, status_msg)
                
                if success and os.path.exists(output_file):
                    # Check file size
                    file_size = os.path.getsize(output_file)
                    
                    if file_size == 0:
                        await message.reply_text(f"❌ Download failed for stream {idx}: Empty file")
                        os.remove(output_file)
                        continue
                        
                    if file_size > 2 * 1024 * 1024 * 1024:  # 2GB limit
                        await message.reply_text(f"❌ Stream {idx} too large (>2GB)")
                        os.remove(output_file)
                        continue
                    
                    # Send file
                    await status_msg.edit_text(f"📤 Uploading stream {idx}/{len(links)}...")
                    await message.reply_document(
                        output_file,
                        caption=f"🎥 Stream {idx}/{len(links)}\nSource: `{url}`"
                    )
                    os.remove(output_file)
                else:
                    await message.reply_text(f"❌ Failed to download stream {idx}")

            except Exception as e:
                logger.error(f"Error processing URL {idx}: {str(e)}")
                await message.reply_text(f"❌ Error processing stream {idx}:\n`{str(e)}`")
                if os.path.exists(output_file):
                    os.remove(output_file)

        await status_msg.edit_text("✅ All streams processed!")

    except Exception as e:
        await message.reply_text(f"❌ Error: `{str(e)}`")
        logger.error(f"M3U8 handler error: {str(e)}")
