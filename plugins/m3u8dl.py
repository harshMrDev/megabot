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
START_TIME = "2025-06-18 16:11:24"
ADMIN_USERNAME = "harshMrDev"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Headers for CloudFront
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Origin': 'https://dj32a0fpanqm7.cloudfront.net',
    'Referer': 'https://dj32a0fpanqm7.cloudfront.net/',
}

async def fetch_playlist(session, url):
    """Fetch M3U8 playlist with proper headers"""
    try:
        async with session.get(url, headers=HEADERS, timeout=30) as response:
            if response.status != 200:
                logger.error(f"Failed to fetch playlist: HTTP {response.status}")
                return None
            
            content = await response.text()
            logger.info(f"Playlist content length: {len(content)}")
            logger.info(f"First 100 chars: {content[:100]}")
            return content
    except Exception as e:
        logger.error(f"Error fetching playlist: {str(e)}")
        return None

async def download_segment(session, url, output_file):
    """Download a single segment"""
    try:
        async with session.get(url, headers=HEADERS) as response:
            if response.status == 200:
                data = await response.read()
                async with aiofiles.open(output_file, 'ab') as f:
                    await f.write(data)
                return True
            logger.error(f"Segment download failed: HTTP {response.status}")
            return False
    except Exception as e:
        logger.error(f"Segment download error: {str(e)}")
        return False

async def process_m3u8(url, output_file, status_msg):
    """Process M3U8 playlist"""
    try:
        async with aiohttp.ClientSession() as session:
            # Fetch initial playlist
            content = await fetch_playlist(session, url)
            if not content:
                await status_msg.edit_text("❌ Failed to fetch playlist")
                return False

            playlist = m3u8.loads(content)
            logger.info(f"Playlist type: {'Master' if playlist.is_endlist else 'Media'}")
            
            # Handle master playlist
            if playlist.playlists:
                logger.info("Processing master playlist...")
                # Get highest quality variant
                variants = sorted(playlist.playlists, key=lambda p: p.stream_info.bandwidth if p.stream_info else 0)
                chosen_playlist = variants[-1]
                
                # Get variant playlist URL
                variant_url = chosen_playlist.uri
                if not variant_url.startswith('http'):
                    variant_url = urljoin(url, variant_url)
                
                logger.info(f"Selected variant: {variant_url}")
                
                # Fetch media playlist
                content = await fetch_playlist(session, variant_url)
                if not content:
                    await status_msg.edit_text("❌ Failed to fetch media playlist")
                    return False
                
                playlist = m3u8.loads(content)
                url = variant_url

            # Check segments
            if not playlist.segments:
                logger.error("No segments found in playlist")
                logger.error(f"Playlist content: {content}")
                await status_msg.edit_text("❌ No segments found in playlist")
                return False

            base_url = url.rsplit('/', 1)[0] + '/'
            total_segments = len(playlist.segments)
            
            logger.info(f"Found {total_segments} segments")
            await status_msg.edit_text(
                f"📥 Found {total_segments} segments\n"
                "⏳ Starting download..."
            )

            # Download segments
            if os.path.exists(output_file):
                os.remove(output_file)

            for idx, segment in enumerate(playlist.segments, 1):
                segment_url = urljoin(base_url, segment.uri)
                success = await download_segment(session, segment_url, output_file)
                
                if not success:
                    logger.error(f"Failed to download segment {idx}")
                    continue

                if idx % 5 == 0 or idx == total_segments:
                    progress = (idx / total_segments) * 100
                    await status_msg.edit_text(
                        f"📥 Downloading: {progress:.1f}%\n"
                        f"Segments: {idx}/{total_segments}"
                    )

            # Verify file
            if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                await status_msg.edit_text("❌ Download failed - Empty file")
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
