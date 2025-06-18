import os
import re
import m3u8
import aiohttp
import aiofiles
import asyncio
import logging
from datetime import datetime
from urllib.parse import urljoin, urlparse
from pyrogram import Client, filters
from pyrogram.types import Message

# Constants
START_TIME = "2025-06-18 16:02:02"
ADMIN_USERNAME = "harshMrDev"
CHUNK_SIZE = 1024*1024  # 1MB chunks
MAX_RETRIES = 3

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# M3U8 URL pattern
M3U8_REGEX = r'https?://[^\s<>"]+?\.m3u8(?:\?[^\s<>"]*)?'

def get_base_url(url):
    """Get base URL for relative paths"""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{os.path.dirname(parsed.path)}/"

async def download_segment(session, url, base_url, output_file):
    """Download a single segment"""
    full_url = urljoin(base_url, url) if not url.startswith('http') else url
    
    for retry in range(MAX_RETRIES):
        try:
            async with session.get(full_url) as response:
                if response.status == 200:
                    async with aiofiles.open(output_file, 'ab') as f:
                        await f.write(await response.read())
                    return True
        except Exception as e:
            logger.error(f"Segment download error (attempt {retry+1}): {str(e)}")
            if retry < MAX_RETRIES - 1:
                await asyncio.sleep(1)
    return False

async def process_m3u8(url, output_file, status_msg):
    """Process M3U8 playlist and download segments"""
    try:
        async with aiohttp.ClientSession() as session:
            # Get M3U8 playlist
            async with session.get(url) as response:
                if response.status != 200:
                    raise Exception(f"Failed to get playlist: {response.status}")
                
                playlist_text = await response.text()
                playlist = m3u8.loads(playlist_text)
                
                # Handle master playlist
                if playlist.is_endlist and playlist.playlists:
                    # Get highest quality stream
                    playlist_url = playlist.playlists[-1].uri
                    if not playlist_url.startswith('http'):
                        playlist_url = urljoin(url, playlist_url)
                    
                    # Get actual playlist
                    async with session.get(playlist_url) as sub_response:
                        if sub_response.status != 200:
                            raise Exception(f"Failed to get sub-playlist: {sub_response.status}")
                        playlist = m3u8.loads(await sub_response.text())
                        url = playlist_url  # Update base URL

                if not playlist.segments:
                    raise Exception("No segments found in playlist")

                base_url = get_base_url(url)
                total_segments = len(playlist.segments)
                
                await status_msg.edit_text(
                    f"📥 Found {total_segments} segments\n"
                    "⏳ Starting download..."
                )

                # Create fresh output file
                if os.path.exists(output_file):
                    os.remove(output_file)

                # Download segments
                for idx, segment in enumerate(playlist.segments, 1):
                    success = await download_segment(
                        session, 
                        segment.uri, 
                        base_url, 
                        output_file
                    )
                    
                    if not success:
                        raise Exception(f"Failed to download segment {idx}")

                    # Update progress every 5 segments
                    if idx % 5 == 0 or idx == total_segments:
                        progress = idx * 100 / total_segments
                        await status_msg.edit_text(
                            f"📥 Downloading: {progress:.1f}%\n"
                            f"Segments: {idx}/{total_segments}"
                        )

                return True

    except Exception as e:
        logger.error(f"M3U8 processing error: {str(e)}")
        await status_msg.edit_text(f"❌ Download failed: {str(e)}")
        return False

@Client.on_message(filters.command("m3u8"))
async def m3u8_command(client, message):
    """Handle /m3u8 command"""
    await message.reply_text(
        "📥 **M3U8 Stream Downloader**\n\n"
        "Send me:\n"
        "• Direct M3U8 URL or\n"
        "• Text file with M3U8 URLs\n\n"
        "I will download and send the videos to you!"
    )

@Client.on_message((filters.regex(M3U8_REGEX) | filters.document) & filters.private)
async def handle_m3u8(client, message):
    """Handle M3U8 URLs or text files"""
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

                output_file = f"stream_{message.from_user.id}_{int(datetime.now().timestamp())}.ts"
                
                # Process M3U8
                success = await process_m3u8(url, output_file, status_msg)
                
                if success and os.path.exists(output_file):
                    file_size = os.path.getsize(output_file)
                    
                    if file_size == 0:
                        await message.reply_text(f"❌ Stream {idx} is empty")
                        os.remove(output_file)
                        continue
                        
                    if file_size > 2000 * 1024 * 1024:  # 2GB limit
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
                logger.error(f"Error processing stream {idx}: {str(e)}")
                await message.reply_text(f"❌ Error processing stream {idx}:\n`{str(e)}`")
                if os.path.exists(output_file):
                    os.remove(output_file)

        await status_msg.edit_text("✅ All streams processed!")

    except Exception as e:
        await message.reply_text(f"❌ Error: `{str(e)}`")
        logger.error(f"M3U8 handler error: {str(e)}")
