import os
import re
import m3u8
import time
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
START_TIME = "2025-06-18 18:47:57"
ADMIN_USERNAME = "harshMrDev"
MAX_CONCURRENT_DOWNLOADS = 10
CHUNK_SIZE = 1024 * 1024

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Headers for requests
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': '*/*',
}

def create_progress_bar(current, total, bar_length=20):
    """Create a progress bar string"""
    progress = float(current) / total
    filled_length = int(bar_length * progress)
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    percent = round(progress * 100, 1)
    return f"[{bar}] {percent}%"

def humanbytes(size):
    """Convert bytes to human readable format"""
    if not size:
        return "0B"
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(size) < 1024.0:
            return f"{size:3.1f}{unit}B"
        size /= 1024.0
    return f"{size:.1f}YB"

def time_formatter(seconds):
    """Format seconds into readable time"""
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}h:{minutes:02d}m:{seconds:02d}s"

async def handle_flood_wait(e, message):
    """Handle FloodWait error"""
    try:
        wait_time = int(str(e).split('wait of ')[1].split(' seconds')[0])
        await message.edit_text(
            f"⏳ Telegram rate limit reached.\n"
            f"Waiting for {wait_time} seconds..."
        )
        await asyncio.sleep(wait_time)
        return True
    except Exception as e:
        logger.error(f"Error handling flood wait: {str(e)}")
        return False

async def progress(current, total, message, start, text):
    """Update progress bar for uploads"""
    try:
        if round(current / total * 100, 0) % 5 == 0:
            now = time.time()
            diff = now - start
            if diff > 1:
                speed = current / diff
                if speed > 0:
                    eta = (total - current) / speed
                else:
                    eta = 0
                
                progress_bar = create_progress_bar(current, total)
                try:
                    await message.edit_text(
                        f"{text}\n"
                        f"{progress_bar}\n"
                        f"📊 Progress: {current * 100 / total:.1f}%\n"
                        f"🚀 Speed: {humanbytes(speed)}/s\n"
                        f"⏱ ETA: {time_formatter(eta)}"
                    )
                except Exception as e:
                    if "420 FLOOD_WAIT" in str(e):
                        await handle_flood_wait(e, message)
    except Exception as e:
        logger.error(f"Progress update error: {str(e)}")

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
            
            try:
                await status_msg.edit_text(
                    f"📥 Found {total_segments} segments\n"
                    "⏳ Starting download..."
                )
            except Exception as e:
                if "420 FLOOD_WAIT" in str(e):
                    await handle_flood_wait(e, status_msg)

            # Clean up existing file
            if os.path.exists(output_file):
                os.remove(output_file)

            # Download segments with progress bar
            start_time = time.time()
            for idx, segment in enumerate(playlist.segments, 1):
                segment_url = urljoin(base_url, segment.uri)
                success = await download_segment(session, segment_url, output_file)
                
                if not success:
                    logger.error(f"Failed to download segment {idx}")
                    continue

                if idx % 5 == 0 or idx == total_segments:
                    now = time.time()
                    elapsed_time = now - start_time
                    speed = idx / elapsed_time if elapsed_time > 0 else 0
                    eta = (total_segments - idx) / speed if speed > 0 else 0
                    
                    progress_bar = create_progress_bar(idx, total_segments)
                    try:
                        await status_msg.edit_text(
                            f"📥 Downloading segments\n"
                            f"{progress_bar}\n"
                            f"🔄 Progress: {idx}/{total_segments} ({idx/total_segments*100:.1f}%)\n"
                            f"🚀 Speed: {idx/elapsed_time:.1f} segments/s\n"
                            f"⏱ ETA: {time_formatter(eta)}"
                        )
                    except Exception as e:
                        if "420 FLOOD_WAIT" in str(e):
                            await handle_flood_wait(e, status_msg)

            # Verify download
            if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                raise Exception("Download failed - Empty file")

            return output_file

    except Exception as e:
        logger.error(f"M3U8 processing error: {str(e)}")
        if status_msg:
            try:
                await status_msg.edit_text(f"❌ Error: {str(e)}")
            except Exception as e2:
                if "420 FLOOD_WAIT" in str(e2):
                    await handle_flood_wait(e2, status_msg)
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
    
    try:
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as file:
            content = await file.read()
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            
            i = 0
            while i < len(lines):
                line = lines[i]
                
                # Handle video entries with [Category] Title format
                if '.m3u8' in line:
                    # Split on last occurrence of ':http'
                    parts = line.rsplit(':http', 1)
                    if len(parts) == 2:
                        title = parts[0].strip()
                        url = 'http' + parts[1].strip()
                        
                        # Keep the original format with square brackets
                        entries.append({
                            'type': 'video',
                            'title': title,
                            'url': url
                        })
                        logger.info(f"Found video: {title[:50]}... | {url[:50]}...")
                
                # Handle PDF entries
                elif line.startswith('PDF -'):
                    pdf_title = line[5:].strip()  # Remove 'PDF -' prefix
                    if ':' in pdf_title:
                        pdf_title = pdf_title.split(':', 1)[1].strip()
                    
                    # Get the next line which should be the PDF URL
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if next_line.startswith(('http://', 'https://')) and '.pdf' in next_line:
                            entries.append({
                                'type': 'pdf',
                                'title': pdf_title,
                                'url': next_line
                            })
                            logger.info(f"Found PDF: {pdf_title[:50]}... | {next_line[:50]}...")
                            i += 1  # Skip the URL line
                
                i += 1
                
        total_videos = sum(1 for entry in entries if entry['type'] == 'video')
        total_pdfs = sum(1 for entry in entries if entry['type'] == 'pdf')
        logger.info(f"Parsed {len(entries)} total entries: {total_videos} videos, {total_pdfs} PDFs")
        
        # Log first few entries for debugging
        for idx, entry in enumerate(entries[:3]):
            logger.info(f"Entry {idx+1}: {entry['type']} - {entry['title'][:50]}... | {entry['url'][:50]}...")
        
        return entries
    except Exception as e:
        logger.error(f"Error parsing file: {str(e)}")
        logger.error(f"File content preview: {content[:200] if 'content' in locals() else 'No content'}")
        return []

def clean_filename(title):
    """Clean filename from invalid characters"""
    if not title:
        return datetime.now().strftime("Video_%Y%m%d_%H%M%S")
    
    # Keep the square brackets for category
    # Remove only invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        title = title.replace(char, '_')
    
    # Clean up whitespace and dots
    title = ' '.join(title.split())
    title = title.strip('. ')
    
    # Limit length while preserving the category in brackets
    if len(title) > 200:
        bracket_end = title.find(']')
        if bracket_end != -1:
            category = title[:bracket_end+1]
            rest = title[bracket_end+1:].strip()
            # Ensure we don't exceed 200 chars while keeping the category
            available_space = 197 - len(category)  # 197 to account for " - "
            if available_space > 0:
                title = f"{category} - {rest[:available_space]}"
            else:
                title = title[:200]
        else:
            title = title[:200]
    
    return title

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
                await message.reply_text("❌ No valid entries found in file. Please check the format.")
                return

            total = len(entries)
            status_msg = await message.reply_text(
                f"🔍 Found {total} entries\n"
                "⏳ Processing in order..."
            )

            async with aiohttp.ClientSession() as session:
                i = 0
                while i < len(entries):
                    try:
                        entry = entries[i]
                        if entry['type'] == 'video':
                            # Process video
                            title = entry['title']
                            url = entry['url']
                            clean_title = clean_filename(title)
                            
                            try:
                                await status_msg.edit_text(
                                    f"📥 Processing video {i+1}/{total}\n"
                                    f"Title: {clean_title}"
                                )
                            except Exception as e:
                                if "420 FLOOD_WAIT" in str(e):
                                    if await handle_flood_wait(e, status_msg):
                                        continue
                                    else:
                                        raise e

                            # Download video
                            ts_file = f"temp_{message.from_user.id}_{int(datetime.now().timestamp())}.ts"
                            downloaded_file = await process_m3u8(url, ts_file, status_msg)
                            
                            if downloaded_file and os.path.exists(downloaded_file):
                                # Convert video
                                try:
                                    await status_msg.edit_text(f"🔄 Converting: {clean_title}")
                                except Exception as e:
                                    if "420 FLOOD_WAIT" in str(e):
                                        await handle_flood_wait(e, status_msg)
                                        
                                result_file = await convert_to_format(downloaded_file, output_format)
                                
                                if result_file and os.path.exists(result_file):
                                    # Upload video with progress
                                    start_time = time.time()
                                    try:
                                        await message.reply_document(
                                            result_file,
                                            caption=f"🎥 {clean_title}",
                                            file_name=f"{clean_title}.{output_format}",
                                            progress=progress,
                                            progress_args=(
                                                status_msg,
                                                start_time,
                                                f"📤 Uploading: {clean_title}"
                                            )
                                        )
                                    except Exception as e:
                                        if "420 FLOOD_WAIT" in str(e):
                                            if await handle_flood_wait(e, status_msg):
                                                continue
                                            else:
                                                raise e
                                    os.remove(result_file)
                            
                            # Look ahead for associated PDFs
                            next_idx = i + 1
                            while next_idx < len(entries) and entries[next_idx]['type'] == 'pdf':
                                pdf_entry = entries[next_idx]
                                if pdf_entry['title'].strip() == title.strip():
                                    pdf_url = pdf_entry['url']
                                    
                                    try:
                                        await status_msg.edit_text(
                                            f"📥 Downloading PDF for: {clean_title}"
                                        )
                                    except Exception as e:
                                        if "420 FLOOD_WAIT" in str(e):
                                            if await handle_flood_wait(e, status_msg):
                                                continue
                                            else:
                                                raise e
                                    
                                    pdf_path = f"temp_pdf_{message.from_user.id}_{int(datetime.now().timestamp())}.pdf"
                                    if await download_pdf(session, pdf_url, pdf_path):
                                        # Upload PDF with progress
                                        start_time = time.time()
                                        try:
                                            await message.reply_document(
                                                pdf_path,
                                                caption=f"📚 {clean_title}",
                                                file_name=f"{clean_title}.pdf",
                                                progress=progress,
                                                progress_args=(
                                                    status_msg,
                                                    start_time,
                                                    f"📤 Uploading PDF: {clean_title}"
                                                )
                                            )
                                        except Exception as e:
                                            if "420 FLOOD_WAIT" in str(e):
                                                if await handle_flood_wait(e, status_msg):
                                                    continue
                                                else:
                                                    raise e
                                        os.remove(pdf_path)
                                    else:
                                        await message.reply_text(f"❌ Failed to download PDF for: {clean_title}")
                                    
                                    next_idx += 1
                                    i = next_idx - 1
                                else:
                                    break
                            
                        i += 1

                    except Exception as e:
                        if "420 FLOOD_WAIT" in str(e):
                            if await handle_flood_wait(e, status_msg):
                                continue
                            else:
                                raise e
                        else:
                            logger.error(f"Error processing entry {i+1}: {str(e)}")
                            await message.reply_text(f"❌ Error processing: {clean_title}\n`{str(e)}`")
                            # Clean up files
                            for f in [ts_file, result_file]:
                                if 'f' in locals() and os.path.exists(f):
                                    os.remove(f)
                            i += 1
                    
                    # Add longer delay between entries to avoid flood
                    await asyncio.sleep(3)

            try:
                await status_msg.edit_text("✅ All files processed in order!")
            except Exception as e:
                if "420 FLOOD_WAIT" in str(e):
                    await handle_flood_wait(e, status_msg)

        else:  # Single URL
            status_msg = await message.reply_text("⏳ Processing...")
            
            base_output = f"video_{message.from_user.id}_{int(datetime.now().timestamp())}"
            ts_file = f"{base_output}.ts"
            
            downloaded_file = await process_m3u8(message.text, ts_file, status_msg)
            
            if downloaded_file and os.path.exists(downloaded_file):
                try:
                    await status_msg.edit_text("🔄 Converting...")
                except Exception as e:
                    if "420 FLOOD_WAIT" in str(e):
                        await handle_flood_wait(e, status_msg)
                        
                result_file = await convert_to_format(downloaded_file, output_format)
                
                if result_file and os.path.exists(result_file):
                    # Upload with progress
                    start_time = time.time()
                    try:
                        await message.reply_document(
                            result_file,
                            caption="🎥 Video",
                            file_name=f"video.{output_format}",
                            progress=progress,
                            progress_args=(
                                status_msg,
                                start_time,
                                "📤 Uploading..."
                            )
                        )
                    except Exception as e:
                        if "420 FLOOD_WAIT" in str(e):
                            if await handle_flood_wait(e, status_msg):
                                await message.reply_document(
                                    result_file,
                                    caption="🎥 Video",
                                    file_name=f"video.{output_format}",
                                    progress=progress,
                                    progress_args=(
                                        status_msg,
                                        time.time(),
                                        "📤 Uploading..."
                                    )
                                )
                    os.remove(result_file)
                else:
                    await message.reply_text("❌ Conversion failed")
            else:
                await message.reply_text("❌ Download failed")

    except Exception as e:
        if "420 FLOOD_WAIT" in str(e):
            await handle_flood_wait(e, message)
        else:
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
