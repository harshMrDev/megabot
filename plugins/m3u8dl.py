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
START_TIME = "2025-06-18 19:11:14"
ADMIN_USERNAME = "harshMrDev"
MAX_CONCURRENT_DOWNLOADS = 5
MIN_DELAY_BETWEEN_UPDATES = 5  # Minimum seconds between status updates
MIN_DELAY_BETWEEN_ENTRIES = 10  # Minimum seconds between processing entries
CHUNK_SIZE = 1024 * 1024  # 1 MB

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Headers for requests
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': '*/*',
}

# Track last update times
last_progress_update = {}
last_status_update = {}
last_message_update = {}

async def safe_edit_message(message, text, sleep_on_flood=True):
    """Safely edit message with flood control"""
    try:
        now = time.time()
        message_id = f"{message.chat.id}:{message.id}"
        
        if message_id in last_message_update:
            time_since_last = now - last_message_update[message_id]
            if time_since_last < MIN_DELAY_BETWEEN_UPDATES:
                await asyncio.sleep(MIN_DELAY_BETWEEN_UPDATES - time_since_last)
        
        await message.edit_text(text)
        last_message_update[message_id] = now
        
    except Exception as e:
        if "FLOOD_WAIT" in str(e):
            if sleep_on_flood:
                wait_time = int(str(e).split('wait of ')[1].split(' seconds')[0])
                logger.info(f"FloodWait: {wait_time} seconds")
                await asyncio.sleep(wait_time + 5)
                return await safe_edit_message(message, text, False)
        else:
            logger.error(f"Message edit error: {str(e)}")

def clean_filename(title):
    """Clean filename from invalid characters while preserving category"""
    if not title:
        return datetime.now().strftime("Video_%Y%m%d_%H%M%S")
    
    # Keep category in brackets
    bracket_end = title.find(']')
    if bracket_end != -1:
        category = title[:bracket_end+1]
        rest = title[bracket_end+1:].strip()
        
        # Clean the rest of the title
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            rest = rest.replace(char, '_')
        
        # Combine with length limit
        if len(category) + len(rest) > 200:
            available_space = 197 - len(category)  # 197 to account for " - "
            if available_space > 0:
                title = f"{category} - {rest[:available_space]}"
            else:
                title = title[:200]
        else:
            title = f"{category} - {rest}"
    else:
        # Clean title without category
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            title = title.replace(char, '_')
        title = title[:200]
    
    return title.strip('. ')

def create_progress_bar(current, total, bar_length=20):
    """Create a progress bar string"""
    if total == 0:
        return "[░" * bar_length + "] 0%"
    progress = float(current) / total
    filled_length = int(bar_length * progress)
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    percent = round(progress * 100, 1)
    return f"[{bar}] {percent}%"

def humanbytes(size):
    """Convert bytes to human readable format"""
    if not size:
        return "0B"
    units = ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']
    for unit in units:
        if abs(size) < 1024.0:
            return f"{size:3.1f}{unit}B"
        size /= 1024.0
    return f"{size:.1f}YB"

def time_formatter(seconds):
    """Format seconds into readable time"""
    if not seconds:
        return "0s"
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}h:{minutes:02d}m:{seconds:02d}s"

async def handle_flood_wait(e, message, retry_action=None):
    """Enhanced FloodWait handler with retry support"""
    try:
        if "FLOOD_WAIT" in str(e):
            wait_time = int(str(e).split('wait of ')[1].split(' seconds')[0])
            logger.info(f"FloodWait detected: waiting for {wait_time} seconds")
            
            try:
                await safe_edit_message(
                    message,
                    f"⏳ Rate limit reached\n"
                    f"Waiting for {time_formatter(wait_time)}...\n"
                    f"Bot will automatically resume after the wait time."
                )
            except Exception:
                pass
            
            await asyncio.sleep(wait_time + 5)
            
            if retry_action:
                try:
                    await retry_action()
                    return True
                except Exception as retry_error:
                    logger.error(f"Retry action failed: {str(retry_error)}")
                    return False
            
            return True
        return False
    except Exception as e:
        logger.error(f"Error handling flood wait: {str(e)}")
        return False

async def progress(current, total, message, start, text):
    """Update progress bar with rate limiting"""
    try:
        now = time.time()
        message_id = f"{message.chat.id}:{message.id}"
        
        if message_id not in last_progress_update:
            last_progress_update[message_id] = 0
        
        if now - last_progress_update[message_id] < MIN_DELAY_BETWEEN_UPDATES:
            return
        
        if total is None:
            total = current
        
        if current <= 0 or total <= 0:
            return
        
        diff = now - start
        speed = current / diff if diff > 0 else 0
        eta = (total - current) / speed if speed > 0 else 0
        
        progress_bar = create_progress_bar(current, total)
        
        try:
            await safe_edit_message(
                message,
                f"{text}\n"
                f"{progress_bar}\n"
                f"📊 Progress: {current * 100 / total:.1f}%\n"
                f"🚀 Speed: {humanbytes(speed)}/s\n"
                f"⏱ ETA: {time_formatter(eta)}"
            )
            last_progress_update[message_id] = now
        except Exception as e:
            if "FLOOD_WAIT" in str(e):
                async def retry():
                    await safe_edit_message(
                        message,
                        f"{text}\n{progress_bar}\n"
                        f"📊 Progress: {current * 100 / total:.1f}%"
                    )
                await handle_flood_wait(e, message, retry)
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
    """Process M3U8 playlist with rate-limited updates"""
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
                    content = await response.text()
                    playlist = m3u8.loads(content)
                    url = variant_url

            if not playlist.segments:
                raise Exception("No segments found in playlist")

            total_segments = len(playlist.segments)
            base_url = url.rsplit('/', 1)[0] + '/'
            
            await safe_edit_message(
                status_msg,
                f"📥 Found {total_segments} segments\n"
                "⏳ Starting download..."
            )

            # Clean up existing file
            if os.path.exists(output_file):
                os.remove(output_file)

            # Download segments with progress bar
            start_time = time.time()
            last_update_time = 0
            for idx, segment in enumerate(playlist.segments, 1):
                segment_url = urljoin(base_url, segment.uri)
                success = await download_segment(session, segment_url, output_file)
                
                if not success:
                    logger.error(f"Failed to download segment {idx}")
                    continue

                now = time.time()
                if (idx % 10 == 0 or idx == total_segments) and now - last_update_time >= MIN_DELAY_BETWEEN_UPDATES:
                    progress = idx / total_segments
                    progress_bar = create_progress_bar(idx, total_segments)
                    speed = idx / (now - start_time) if now > start_time else 0
                    eta = (total_segments - idx) / speed if speed > 0 else 0
                    
                    try:
                        await safe_edit_message(
                            status_msg,
                            f"📥 Downloading segments\n"
                            f"{progress_bar}\n"
                            f"🔄 {idx}/{total_segments} ({progress*100:.1f}%)\n"
                            f"🚀 Speed: {speed:.1f} segments/s\n"
                            f"⏱ ETA: {time_formatter(eta)}"
                        )
                        last_update_time = now
                    except Exception as e:
                        if "FLOOD_WAIT" in str(e):
                            await handle_flood_wait(e, status_msg)
                            last_update_time = time.time()

            # Verify download
            if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                raise Exception("Download failed - Empty file")

            return output_file

    except Exception as e:
        logger.error(f"M3U8 processing error: {str(e)}")
        if status_msg:
            await safe_edit_message(status_msg, f"❌ Error: {str(e)}")
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
                    parts = line.rsplit(':http', 1)
                    if len(parts) == 2:
                        title = parts[0].strip()
                        url = 'http' + parts[1].strip()
                        entries.append({
                            'type': 'video',
                            'title': title,
                            'url': url
                        })
                        logger.info(f"Found video: {title[:50]}... | {url[:50]}...")
                
                # Handle PDF entries
                elif line.startswith('PDF -'):
                    pdf_title = line[5:].strip()
                    if ':' in pdf_title:
                        pdf_title = pdf_title.split(':', 1)[1].strip()
                    
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if next_line.startswith(('http://', 'https://')) and '.pdf' in next_line:
                            entries.append({
                                'type': 'pdf',
                                'title': pdf_title,
                                'url': next_line
                            })
                            logger.info(f"Found PDF: {pdf_title[:50]}... | {next_line[:50]}...")
                            i += 1
                
                i += 1
                
        total_videos = sum(1 for entry in entries if entry['type'] == 'video')
        total_pdfs = sum(1 for entry in entries if entry['type'] == 'pdf')
        logger.info(f"Found {total_videos} videos and {total_pdfs} PDFs")
        return entries

    except Exception as e:
        logger.error(f"Error parsing file: {str(e)}")
        return []

async def convert_to_format(input_file, output_format='mp4'):
    """Convert file to specified format using FFmpeg"""
    try:
        output_file = input_file.rsplit('.', 1)[0] + f'.{output_format}'
        
        if output_format == 'mp3':
            cmd = [
                'ffmpeg', '-i', input_file,
                '-vn',
                '-acodec', 'libmp3lame',
                '-ab', '192k',
                '-ar', '44100',
                '-y',
                output_file
            ]
        else:
            cmd = [
                'ffmpeg', '-i', input_file,
                '-c', 'copy',
                '-y',
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
                await message.reply_text("❌ No valid entries found in file.")
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
                            title = entry['title']
                            url = entry['url']
                            clean_title = clean_filename(title)
                            
                            await safe_edit_message(
                                status_msg,
                                f"📥 Processing {i+1}/{total}\n"
                                f"Title: {clean_title}"
                            )

                            # Download video
                            ts_file = f"temp_{message.from_user.id}_{int(datetime.now().timestamp())}.ts"
                            downloaded_file = await process_m3u8(url, ts_file, status_msg)
                            
                            if downloaded_file and os.path.exists(downloaded_file):
                                await safe_edit_message(status_msg, f"🔄 Converting: {clean_title}")
                                result_file = await convert_to_format(downloaded_file, output_format)
                                
                                if result_file and os.path.exists(result_file):
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
                                        if "FLOOD_WAIT" in str(e):
                                            await handle_flood_wait(e, status_msg)
                                            continue
                                    finally:
                                        if os.path.exists(result_file):
                                            os.remove(result_file)
                            
                            # Process associated PDFs
                            next_idx = i + 1
                            while next_idx < len(entries) and entries[next_idx]['type'] == 'pdf':
                                pdf_entry = entries[next_idx]
                                if pdf_entry['title'].strip() == title.strip():
                                    pdf_url = pdf_entry['url']
                                    
                                    await safe_edit_message(
                                        status_msg,
                                        f"📥 Downloading PDF for: {clean_title}"
                                    )
                                    
                                    pdf_path = f"temp_pdf_{message.from_user.id}_{int(datetime.now().timestamp())}.pdf"
                                    if await download_pdf(session, pdf_url, pdf_path):
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
                                            if "FLOOD_WAIT" in str(e):
                                                await handle_flood_wait(e, status_msg)
                                                continue
                                        finally:
                                            if os.path.exists(pdf_path):
                                                os.remove(pdf_path)
                                    else:
                                        await message.reply_text(f"❌ Failed to download PDF: {clean_title}")
                                    
                                    next_idx += 1
                                    i = next_idx - 1
                                else:
                                    break
                            
                        i += 1
                        await asyncio.sleep(MIN_DELAY_BETWEEN_ENTRIES)

                    except Exception as e:
                        logger.error(f"Error processing entry {i+1}: {str(e)}")
                        await message.reply_text(f"❌ Error processing entry {i+1}")
                        i += 1
                        # Clean up any remaining files
                        for f in [ts_file, result_file]:
                            if 'f' in locals() and os.path.exists(f):
                                os.remove(f)

            await safe_edit_message(status_msg, "✅ All files processed!")

        else:  # Single URL
            status_msg = await message.reply_text("⏳ Processing...")
            ts_file = f"video_{message.from_user.id}_{int(datetime.now().timestamp())}.ts"
            
            downloaded_file = await process_m3u8(message.text, ts_file, status_msg)
            
            if downloaded_file and os.path.exists(downloaded_file):
                await safe_edit_message(status_msg, "🔄 Converting...")
                result_file = await convert_to_format(downloaded_file, output_format)
                
                if result_file and os.path.exists(result_file):
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
                        if "FLOOD_WAIT" in str(e):
                            await handle_flood_wait(e, status_msg)
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
                    finally:
                        if os.path.exists(result_file):
                            os.remove(result_file)
                else:
                    await message.reply_text("❌ Conversion failed")
            else:
                await message.reply_text("❌ Download failed")

    except Exception as e:
        logger.error(f"Handler error: {str(e)}")
        await message.reply_text(f"❌ Error: {str(e)}")

@Client.on_message(filters.command(["m3u8", "mp3"]))
async def handle_command(client, message):
    """Handle /m3u8 and /mp3 commands"""
    command = message.text.split()[0][1:]
    if command == "mp3":
        await message.reply_text(
            "🎵 **M3U8 Audio Extractor**\n\n"
            "Send me:\n"
            "• Direct M3U8 URL or\n"
            "• Text file with titles and URLs\n\n"
            "Format for text file:\n"
            "[Category] Title 1:URL 1\n"
            "PDF - [Category] Title 1\n"
            "PDF_URL 1\n\n"
            "[Category] Title 2:URL 2"
        )
    else:
        await message.reply_text(
            "📥 **M3U8 Video Downloader**\n\n"
            "Send me:\n"
            "• Direct M3U8 URL or\n"
            "• Text file with titles and URLs\n\n"
            "Format for text file:\n"
            "[Category] Title 1:URL 1\n"
            "PDF - [Category] Title 1\n"
            "PDF_URL 1\n\n"
            "[Category] Title 2:URL 2\n\n"
            "Commands:\n"
            "/m3u8 - Download as MP4\n"
            "/mp3 - Extract audio as MP3"
        )
