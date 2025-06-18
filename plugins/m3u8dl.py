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
START_TIME = "2025-06-18 16:07:28"
ADMIN_USERNAME = "harshMrDev"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def validate_m3u8_url(session, url):
    """Validate M3U8 URL and get playlist"""
    try:
        async with session.get(url, timeout=30) as response:
            if response.status != 200:
                return None, f"HTTP Error: {response.status}"
            
            content = await response.text()
            if "#EXTM3U" not in content:
                return None, "Not a valid M3U8 playlist"
            
            return content, None
    except Exception as e:
        return None, f"Connection error: {str(e)}"

async def download_ts_file(session, url, output_path, progress_callback):
    """Download TS file with progress updates"""
    try:
        async with session.get(url) as response:
            if response.status != 200:
                return False
            
            async with aiofiles.open(output_path, 'wb') as f:
                async for chunk in response.content.iter_chunked(1024*1024):
                    await f.write(chunk)
                    await progress_callback()
            return True
    except:
        return False

async def process_m3u8(url, output_file, status_msg):
    """Process M3U8 playlist"""
    try:
        async with aiohttp.ClientSession() as session:
            # Validate and get playlist
            content, error = await validate_m3u8_url(session, url)
            if error:
                await status_msg.edit_text(f"❌ Error: {error}")
                return False

            # Parse playlist
            playlist = m3u8.loads(content)
            
            # If it's a master playlist, get the highest quality stream
            if playlist.is_endlist and playlist.playlists:
                # Sort by bandwidth and get highest quality
                playlists = sorted(playlist.playlists, key=lambda p: p.stream_info.bandwidth if p.stream_info else 0)
                playlist_url = playlists[-1].uri
                base_url = url.rsplit('/', 1)[0]
                if not playlist_url.startswith('http'):
                    playlist_url = f"{base_url}/{playlist_url}"
                
                # Get actual playlist
                content, error = await validate_m3u8_url(session, playlist_url)
                if error:
                    await status_msg.edit_text(f"❌ Error: {error}")
                    return False
                
                playlist = m3u8.loads(content)
                url = playlist_url

            # Check for segments
            if not playlist.segments:
                await status_msg.edit_text("❌ No segments found in playlist")
                logger.error(f"No segments in playlist: {url}")
                return False

            # Get base URL for segments
            base_url = url.rsplit('/', 1)[0]
            total_segments = len(playlist.segments)
            
            await status_msg.edit_text(
                f"📥 Found {total_segments} segments\n"
                "⏳ Starting download..."
            )

            # Download segments
            downloaded = 0
            async with aiofiles.open(output_file, 'wb') as outfile:
                for idx, segment in enumerate(playlist.segments, 1):
                    segment_url = segment.uri
                    if not segment_url.startswith('http'):
                        segment_url = f"{base_url}/{segment_url}"

                    # Download segment
                    async with session.get(segment_url) as response:
                        if response.status == 200:
                            data = await response.read()
                            await outfile.write(data)
                            downloaded += 1

                            # Update progress
                            if idx % 5 == 0 or idx == total_segments:
                                progress = (idx / total_segments) * 100
                                await status_msg.edit_text(
                                    f"📥 Downloading: {progress:.1f}%\n"
                                    f"Segments: {idx}/{total_segments}"
                                )
                        else:
                            logger.error(f"Failed to download segment {idx}: {response.status}")

            if downloaded == 0:
                await status_msg.edit_text("❌ Failed to download any segments")
                return False

            return True

    except Exception as e:
        logger.error(f"M3U8 processing error: {str(e)}")
        await status_msg.edit_text(f"❌ Error: {str(e)}")
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

@Client.on_message((filters.regex(r'https?://[^\s<>"]+?\.m3u8(?:\?[^\s<>"]*)?') | filters.document) & filters.private)
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
                links.extend(re.findall(r'https?://[^\s<>"]+?\.m3u8(?:\?[^\s<>"]*)?', content))
            os.remove(file)
            
        # Handle direct URL
        elif message.text:
            links = [message.text.strip()]
            
        if not links:
            await message.reply_text(
                "❌ No valid M3U8 URLs found.\n"
                "Please send a valid M3U8 URL or text file containing URLs."
            )
            return

        status_msg = await message.reply_text(
            f"🔍 Found {len(links)} URL(s)\n"
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
                if 'output_file' in locals() and os.path.exists(output_file):
                    os.remove(output_file)

        await status_msg.edit_text("✅ All streams processed!")

    except Exception as e:
        await message.reply_text(f"❌ Error: `{str(e)}`")
        logger.error(f"M3U8 handler error: {str(e)}")
