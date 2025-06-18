import os
import re
import m3u8
import aiohttp
import aiofiles
import asyncio
import logging
from datetime import datetime
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor
from pyrogram import Client, filters
from pyrogram.types import Message

# Constants
START_TIME = "2025-06-18 16:17:25"
ADMIN_USERNAME = "harshMrDev"
MAX_CONCURRENT_DOWNLOADS = 10  # Adjust based on your server capacity
CHUNK_SIZE = 1024 * 1024  # 1MB chunks

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Headers for CloudFront
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': '*/*',
}

async def download_segment_batch(session, segments, base_url, output_file, start_idx, total_segments, status_msg):
    """Download a batch of segments concurrently"""
    tasks = []
    async with aiofiles.open(output_file, 'ab') as f:
        for segment in segments:
            segment_url = urljoin(base_url, segment.uri)
            task = asyncio.create_task(download_single_segment(session, segment_url, f))
            tasks.append(task)
        
        completed = 0
        for task in asyncio.as_completed(tasks):
            try:
                await task
                completed += 1
                if completed % 5 == 0:
                    progress = ((start_idx + completed) / total_segments) * 100
                    await status_msg.edit_text(
                        f"📥 Downloading: {progress:.1f}%\n"
                        f"Segments: {start_idx + completed}/{total_segments}"
                    )
            except Exception as e:
                logger.error(f"Segment download error: {str(e)}")

async def download_single_segment(session, url, file):
    """Download a single segment"""
    try:
        async with session.get(url, headers=HEADERS) as response:
            if response.status == 200:
                async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                    await file.write(chunk)
                return True
    except Exception as e:
        logger.error(f"Segment download error: {str(e)}")
        return False

async def process_m3u8(url, output_file, status_msg):
    """Process M3U8 playlist with concurrent downloads"""
    try:
        connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_DOWNLOADS)
        timeout = aiohttp.ClientTimeout(total=None, connect=10, sock_connect=10, sock_read=10)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # Fetch playlist
            async with session.get(url, headers=HEADERS) as response:
                if response.status != 200:
                    raise Exception(f"Failed to fetch playlist: {response.status}")
                content = await response.text()

            playlist = m3u8.loads(content)
            
            # Handle master playlist
            if playlist.playlists:
                variant = max(playlist.playlists, key=lambda p: p.stream_info.bandwidth if p.stream_info else 0)
                variant_url = urljoin(url, variant.uri)
                
                async with session.get(variant_url, headers=HEADERS) as response:
                    if response.status != 200:
                        raise Exception("Failed to fetch media playlist")
                    content = await response.text()
                    playlist = m3u8.loads(content)
                    url = variant_url

            if not playlist.segments:
                raise Exception("No segments found in playlist")

            total_segments = len(playlist.segments)
            base_url = url.rsplit('/', 1)[0] + '/'
            
            await status_msg.edit_text(
                f"📥 Found {total_segments} segments\n"
                "⏳ Starting download..."
            )

            # Clean up existing file
            if os.path.exists(output_file):
                os.remove(output_file)

            # Download segments in batches
            batch_size = 10  # Number of segments to download concurrently
            for i in range(0, len(playlist.segments), batch_size):
                batch = playlist.segments[i:i + batch_size]
                await download_segment_batch(
                    session, batch, base_url, output_file, i, total_segments, status_msg
                )

            # Verify download
            if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                raise Exception("Download failed - Empty file")

            return True

    except Exception as e:
        logger.error(f"M3U8 processing error: {str(e)}")
        await status_msg.edit_text(f"❌ Error: {str(e)}")
        return False

@Client.on_message((filters.regex(r'https?://[^\s<>"]+?\.m3u8(?:\?[^\s<>"]*)?') | filters.document) & filters.private)
async def handle_m3u8(client, message):
    """Handle M3U8 URLs or text files"""
    try:
        links = []
        
        # Handle text file
        if message.document and message.document.mime_type == "text/plain":
            file = await message.download()
            with open(file, 'r') as f:
                content = f.read()
                links.extend(re.findall(r'https?://[^\s<>"]+?\.m3u8(?:\?[^\s<>"]*)?', content))
            os.remove(file)
            
        # Handle direct URL
        elif message.text:
            links = [message.text.strip()]
            
        if not links:
            await message.reply_text("❌ No valid M3U8 URLs found")
            return

        status_msg = await message.reply_text(
            f"🔍 Found {len(links)} URL(s)\n"
            "⏳ Processing..."
        )

        for idx, url in enumerate(links, 1):
            try:
                output_file = f"stream_{message.from_user.id}_{int(datetime.now().timestamp())}.ts"
                
                await status_msg.edit_text(
                    f"📥 Processing stream {idx}/{len(links)}\n"
                    f"URL: `{url}`"
                )

                success = await process_m3u8(url, output_file, status_msg)
                
                if success and os.path.exists(output_file):
                    file_size = os.path.getsize(output_file)
                    
                    if file_size == 0:
                        await message.reply_text(f"❌ Stream {idx} is empty")
                    elif file_size > 2000 * 1024 * 1024:  # 2GB limit
                        await message.reply_text(f"❌ Stream {idx} too large (>2GB)")
                    else:
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
                if 'output_file' in locals() and os.path.exists(output_file):
                    os.remove(output_file)

        await status_msg.edit_text("✅ All streams processed!")

    except Exception as e:
        await message.reply_text(f"❌ Error: `{str(e)}`")
        logger.error(f"M3U8 handler error: {str(e)}")

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
