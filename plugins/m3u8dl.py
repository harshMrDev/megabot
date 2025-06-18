import os
import re
import m3u8
import aiohttp
import aiofiles
import asyncio
import logging
import subprocess
from datetime import datetime
from urllib.parse import urljoin, unquote
from pyrogram import Client, filters
from pyrogram.types import Message

# Constants
START_TIME = "2025-06-18 18:04:39"
ADMIN_USERNAME = "harshMrDev"
MAX_CONCURRENT_DOWNLOADS = 10
CHUNK_SIZE = 1024 * 1024
async def parse_text_file(file_path):
    """Parse text file maintaining exact order of entries"""
    entries = []
    current_title = None
    
    try:
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as file:
            content = await file.read()
            lines = content.split('\n')
            
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                if not line:
                    i += 1
                    continue
                
                # If line contains m3u8, it's a video URL
                if '.m3u8' in line and ':' in line:
                    # The title is before the URL, separated by ':'
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        title = parts[0].strip()
                        url = parts[1].strip()
                        entries.append({
                            'type': 'video',
                            'title': title,
                            'url': url
                        })
                
                # If line starts with 'PDF -' and next line is URL
                elif line.startswith('PDF -') and i + 1 < len(lines):
                    title = line[5:].strip()  # Remove 'PDF -' prefix
                    if ':' in title:
                        title = title.split(':', 1)[1].strip()
                    next_line = lines[i + 1].strip()
                    if next_line.startswith(('http://', 'https://')):
                        entries.append({
                            'type': 'pdf',
                            'title': title,
                            'url': next_line
                        })
                        i += 1  # Skip the URL line since we've processed it
                
                i += 1
                
        logger.info(f"Parsed {len(entries)} entries in order")
        for entry in entries:
            logger.info(f"Type: {entry['type']}, Title: {entry['title'][:50]}...")
        return entries
    except Exception as e:
        logger.error(f"Error parsing file: {str(e)}")
        return []

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Headers for requests
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': '*/*',
}

async def download_segment(session, url, output_file):
    """Download a single segment"""
    try:
        async with session.get(url, headers=HEADERS) as response:
            if response.status == 200:
                async with aiofiles.open(output_file, 'ab') as f:
                    await f.write(await response.read())
                return True
        return False
    except Exception as e:
        logger.error(f"Segment download error: {str(e)}")
        return False

async def process_m3u8(url, output_file, status_msg):
    """Process M3U8 playlist"""
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
                # Get highest quality variant
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

            # Download segments
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

            # Verify download
            if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                raise Exception("Download failed - Empty file")

            return output_file

    except Exception as e:
        logger.error(f"M3U8 processing error: {str(e)}")
        if status_msg:
            await status_msg.edit_text(f"❌ Error: {str(e)}")
        return None

async def download_pdf(session, url, output_path):
    """Download PDF file"""
    try:
        async with session.get(url, headers=HEADERS) as response:
            if response.status == 200:
                async with aiofiles.open(output_path, 'wb') as f:
                    await f.write(await response.read())
                return True
        return False
    except Exception as e:
        logger.error(f"PDF download error: {str(e)}")
        return False

async def parse_text_file(file_path):
    """Parse text file maintaining exact order of entries"""
    entries = []
    current_video = None
    
    try:
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as file:
            async for line in file:
                line = line.strip()
                if not line:
                    continue
                
                if line.startswith('PDF -'):
                    # PDF entry
                    if ':' in line:
                        title = line.split(':', 1)[1].strip()
                        next_line = None
                        async for next_line in file:
                            next_line = next_line.strip()
                            if next_line.startswith(('http://', 'https://')):
                                entries.append({
                                    'type': 'pdf',
                                    'title': title,
                                    'url': next_line
                                })
                                break
                elif line.startswith(('http://', 'https://')):
                    if 'm3u8' in line:
                        current_video = line
                else:
                    # This is a video title
                    if current_video:
                        entries.append({
                            'type': 'video',
                            'title': line,
                            'url': current_video
                        })
                        current_video = None
                    else:
                        current_video = None
                        
        logger.info(f"Parsed {len(entries)} entries in order")
        return entries
    except Exception as e:
        logger.error(f"Error parsing file: {str(e)}")
        return []

def clean_filename(title):
    """Clean filename from invalid characters"""
    if not title:
        return datetime.now().strftime("Video_%Y%m%d_%H%M%S")
        
    # Remove or replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        title = title.replace(char, '_')
    
    # Clean up whitespace and dots
    title = ' '.join(title.split())
    title = title.strip('. ')
    
    # Limit length
    return title[:200]

async def convert_to_format(input_file, output_format='mp4'):
    """Convert file to specified format using FFmpeg"""
    try:
        output_file = input_file.rsplit('.', 1)[0] + f'.{output_format}'
        
        if output_format == 'mp3':
            cmd = [
                'ffmpeg', '-i', input_file,
                '-vn',  # No video
                '-acodec', 'libmp3lame',
                '-ab', '192k',  # Bitrate
                '-ar', '44100',  # Sample rate
                '-y',  # Overwrite output file
                output_file
            ]
        else:  # mp4
            cmd = [
                'ffmpeg', '-i', input_file,
                '-c', 'copy',
                '-y',  # Overwrite output file
                output_file
            ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            os.remove(input_file)
            return output_file
        return None
    except Exception as e:
        logger.error(f"Conversion error: {str(e)}")
        return None

@Client.on_message((filters.regex(r'https?://[^\s<>"]+?\.m3u8(?:\?[^\s<>"]*)?') | filters.document) & filters.private)
async def handle_m3u8(client, message):
    """Handle M3U8 URLs or text files"""
    try:
        output_format = 'mp3' if message.reply_to_message and message.reply_to_message.text and '/mp3' in message.reply_to_message.text else 'mp4'
        
        if message.document and message.document.mime_type == "text/plain":
            status = await message.reply_text("📄 Reading file...")
            file = await message.download()
            entries = await parse_text_file(file)
            os.remove(file)
            
            if not entries:
                await message.reply_text("❌ No valid entries found in file")
                return

            total = len(entries)
            status_msg = await message.reply_text(
                f"🔍 Found {total} entries\n"
                "⏳ Processing in order..."
            )

            async with aiohttp.ClientSession() as session:
                for idx, entry in enumerate(entries, 1):
                    try:
                        entry_type = entry['type']
                        title = entry['title']
                        url = entry['url']
                        clean_title = clean_filename(title)
                        
                        if entry_type == 'video':
                            await status_msg.edit_text(
                                f"📥 Processing video {idx}/{total}\n"
                                f"Title: {clean_title}"
                            )

                            # Download video
                            ts_file = f"temp_{message.from_user.id}_{int(datetime.now().timestamp())}.ts"
                            downloaded_file = await process_m3u8(url, ts_file, status_msg)
                            
                            if downloaded_file and os.path.exists(downloaded_file):
                                # Convert video
                                await status_msg.edit_text(f"🔄 Converting: {clean_title}")
                                result_file = await convert_to_format(downloaded_file, output_format)
                                
                                if result_file and os.path.exists(result_file):
                                    await status_msg.edit_text(f"📤 Uploading: {clean_title}")
                                    await message.reply_document(
                                        result_file,
                                        caption=f"🎥 {clean_title}",
                                        file_name=f"{clean_title}.{output_format}"
                                    )
                                    os.remove(result_file)
                                
                        elif entry_type == 'pdf':
                            await status_msg.edit_text(
                                f"📥 Downloading PDF {idx}/{total}\n"
                                f"Title: {clean_title}"
                            )
                            
                            pdf_path = f"temp_pdf_{message.from_user.id}_{int(datetime.now().timestamp())}.pdf"
                            if await download_pdf(session, url, pdf_path):
                                await message.reply_document(
                                    pdf_path,
                                    caption=f"📚 {clean_title}",
                                    file_name=f"{clean_title}.pdf"
                                )
                                os.remove(pdf_path)

                    except Exception as e:
                        logger.error(f"Error processing entry {idx}: {str(e)}")
                        await message.reply_text(f"❌ Error processing: {clean_title}\n`{str(e)}`")
                        # Clean up files
                        for f in [ts_file, result_file, pdf_path]:
                            if 'f' in locals() and os.path.exists(f):
                                os.remove(f)

            await status_msg.edit_text("✅ All files processed in order!")

        else:  # Single URL
            status_msg = await message.reply_text("⏳ Processing...")
            
            base_output = f"video_{message.from_user.id}_{int(datetime.now().timestamp())}"
            ts_file = f"{base_output}.ts"
            
            downloaded_file = await process_m3u8(message.text, ts_file, status_msg)
            
            if downloaded_file and os.path.exists(downloaded_file):
                await status_msg.edit_text("🔄 Converting...")
                result_file = await convert_to_format(downloaded_file, output_format)
                
                if result_file and os.path.exists(result_file):
                    await status_msg.edit_text("📤 Uploading...")
                    await message.reply_document(
                        result_file,
                        caption="🎥 Video",
                        file_name=f"video.{output_format}"
                    )
                    os.remove(result_file)
                else:
                    await message.reply_text("❌ Conversion failed")
            else:
                await message.reply_text("❌ Download failed")

    except Exception as e:
        await message.reply_text(f"❌ Error: `{str(e)}`")
        logger.error(f"Handler error: {str(e)}")

@Client.on_message(filters.command(["m3u8", "mp3"]))
async def handle_command(client, message):
    """Handle /m3u8 and /mp3 commands"""
    command = message.text.split()[0][1:]  # Remove the '/'
    if command == "mp3":
        await message.reply_text(
            "🎵 **M3U8 Audio Extractor**\n\n"
            "Send me:\n"
            "• Direct M3U8 URL or\n"
            "• Text file with titles and URLs\n\n"
            "Format for text file:\n"
            "Title 1\n"
            "URL 1\n\n"
            "Title 2\n"
            "URL 2"
        )
    else:
        await message.reply_text(
            "📥 **M3U8 Video Downloader**\n\n"
            "Send me:\n"
            "• Direct M3U8 URL or\n"
            "• Text file with titles and URLs\n\n"
            "Format for text file:\n"
            "Title 1\n"
            "URL 1\n\n"
            "Title 2\n"
            "URL 2\n\n"
            "Commands:\n"
            "/m3u8 - Download as MP4\n"
            "/mp3 - Extract audio as MP3"
        )
