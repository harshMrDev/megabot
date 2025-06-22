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
    """Download PDF file with better error handling"""
    try:
        logger.info(f"Attempting to download PDF from: {url}")
        async with session.get(url, headers=HEADERS) as response:
            logger.info(f"PDF download response status: {response.status}")
            if response.status == 200:
                content = await response.read()
                if len(content) > 0:
                    async with aiofiles.open(output_path, 'wb') as f:
                        await f.write(content)
                    logger.info(f"PDF downloaded successfully: {output_path} ({len(content)} bytes)")
                    return True
                else:
                    logger.error("PDF download failed: Empty content")
                    return False
            else:
                logger.error(f"PDF download failed: HTTP {response.status}")
                return False
    except Exception as e:
        logger.error(f"PDF download error: {str(e)}")
        return False

def is_pdf_url(url):
    """Check if URL likely points to a PDF"""
    url_lower = url.lower()
    return (url_lower.endswith('.pdf') or 
            'pdf' in url_lower or 
            'application/pdf' in url_lower or
            '.pdf?' in url_lower)

def is_video_url(url):
    """Check if URL likely points to a video (M3U8)"""
    return '.m3u8' in url.lower()

async def parse_text_file(file_path):
    """Improved text file parser with better PDF recognition"""
    entries = []

    try:
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as file:
            content = await file.read()
            lines = [line.strip() for line in content.split('\n') if line.strip()]

        logger.info(f"📄 Total lines in file: {len(lines)}")

        # First pass: identify all URLs and their types
        url_info = []
        for idx, line in enumerate(lines):
            if 'http' in line:
                # Extract URL from line (handle various formats)
                url_match = re.search(r'https?://[^\s<>"\[\]]+', line)
                if url_match:
                    url = url_match.group()
                    # Get text before URL as potential title
                    title_part = line[:url_match.start()].strip()
                    # Clean up title (remove common separators)
                    title_part = re.sub(r'[:\-\|]+$', '', title_part).strip()

                    url_info.append({
                        'line_idx': idx,
                        'line': line,
                        'url': url,
                        'title_part': title_part,
                        'is_video': is_video_url(url),
                        'is_pdf': is_pdf_url(url)
                    })

        logger.info(f"📊 Found {len(url_info)} URLs")

        # Second pass: group content by video entries
        current_video = None

        for i, line in enumerate(lines):
            line_lower = line.lower()

            # Check if this line contains a video URL
            video_url_info = None
            for url_info_item in url_info:
                if url_info_item['line_idx'] == i and url_info_item['is_video']:
                    video_url_info = url_info_item
                    break

            if video_url_info:
                # Found a video URL - create new entry
                title = video_url_info['title_part']

                # If no title in URL line, look for title in previous lines
                if not title:
                    # Look back up to 3 lines for a title
                    for j in range(max(0, i-3), i):
                        prev_line = lines[j].strip()
                        if prev_line and not any(url_item['line_idx'] == j for url_item in url_info):
                            # This line doesn't contain a URL, might be a title
                            if not prev_line.lower().startswith(('pdf', 'note', 'link')):
                                title = prev_line
                                break

                if not title:
                    title = f"Video_{len(entries)+1}"

                current_video = {
                    'type': 'video',
                    'title': title,
                    'url': video_url_info['url'],
                    'pdfs': []
                }
                entries.append(current_video)
                logger.info(f"🎥 Found video: {title[:50]}...")
                continue

            # Check if this line contains a PDF URL
            pdf_url_info = None
            for url_info_item in url_info:
                if url_info_item['line_idx'] == i and url_info_item['is_pdf']:
                    pdf_url_info = url_info_item
                    break

            if pdf_url_info and current_video:
                # Found a PDF URL - associate with current video
                pdf_title = pdf_url_info['title_part']

                # If no title in URL line, look for title in previous lines or use default
                if not pdf_title:
                    # Look back up to 2 lines for a PDF title
                    for j in range(max(0, i-2), i):
                        prev_line = lines[j].strip()
                        if prev_line and not any(url_item['line_idx'] == j for url_item in url_info):
                            # Check if this looks like a PDF title
                            if (prev_line.lower().startswith('pdf') or 
                                'pdf' in prev_line.lower() or
                                prev_line.startswith('[') or
                                len(prev_line) > 10):  # Reasonable title length
                                pdf_title = prev_line
                                break

                if not pdf_title:
                    pdf_title = f"PDF for {current_video['title']}"

                # Clean PDF title
                pdf_title = re.sub(r'^pdf[\s\-:]*', '', pdf_title, flags=re.IGNORECASE).strip()

                current_video['pdfs'].append({
                    'title': pdf_title,
                    'url': pdf_url_info['url']
                })
                logger.info(f"📚 Associated PDF: {pdf_title[:50]}... with video: {current_video['title'][:30]}...")
                continue

            # Check for standalone PDF indicators (lines that mention PDF but don't have URLs)
            if (current_video and 
                ('pdf' in line_lower or 'document' in line_lower) and 
                'http' not in line and
                len(line) > 5):  # Reasonable length for a title

                # This might be a PDF title, check next few lines for URL
                for j in range(i+1, min(len(lines), i+3)):
                    next_line = lines[j].strip()
                    if 'http' in next_line:
                        # Check if this URL is a PDF
                        for url_info_item in url_info:
                            if url_info_item['line_idx'] == j and url_info_item['is_pdf']:
                                # Found matching PDF URL
                                pdf_title = re.sub(r'^pdf[\s\-:]*', '', line, flags=re.IGNORECASE).strip()
                                current_video['pdfs'].append({
                                    'title': pdf_title,
                                    'url': url_info_item['url']
                                })
                                logger.info(f"📚 Found PDF title-URL pair: {pdf_title[:50]}...")
                                break
                        break

        # Summary
        total_videos = len(entries)
        total_pdfs = sum(len(entry['pdfs']) for entry in entries)
        logger.info(f"📊 FINAL PARSING RESULT:")
        logger.info(f"   📹 Videos found: {total_videos}")
        logger.info(f"   📚 PDFs found: {total_pdfs}")

        # Debug output for first few entries
        for idx, entry in enumerate(entries[:3]):
            logger.info(f"   Entry {idx+1}: {entry['title'][:40]}... ({len(entry['pdfs'])} PDFs)")
            for p_idx, pdf in enumerate(entry['pdfs']):
                logger.info(f"      PDF {p_idx+1}: {pdf['title'][:40]}...")

        return entries

    except Exception as e:
        logger.error(f"Error parsing file: {str(e)}")
        return []

async def convert_to_format_fast(input_file, output_format, enable_streaming=True):
    """Fast conversion with streaming optimization"""
    timestamp = int(time.time())
    output_file = f"converted_{timestamp}.{output_format}"
    try:
        if output_format == 'mp3':
            # Fast MP3 extraction with optimal settings
            cmd = [
                'ffmpeg', '-i', input_file,
                '-vn',  # No video
                '-acodec', 'libmp3lame',
                '-ab', '128k',  # Reduced bitrate for faster encoding
                '-ar', '44100',
                '-ac', '2',  # Stereo
                '-threads', '0',  # Use all available threads
                '-y',
                output_file
            ]
        elif output_format == 'mp4':
            # Optimized MP4 for streaming with fast encoding
            cmd = [
                'ffmpeg', '-i', input_file,
                '-c:v', 'libx264',
                '-preset', 'ultrafast',  # Fastest encoding preset
                '-crf', '28',  # Reasonable quality with fast encoding
                '-profile:v', 'baseline',  # Better compatibility
                '-level', '3.1',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-ac', '2',
                '-movflags', '+faststart',  # Enable streaming
                '-threads', '0',  # Use all available threads
                '-y',
                output_file
            ]
        else:
            # Copy streams for other formats (fastest)
            cmd = [
                'ffmpeg', '-i', input_file,
                '-c', 'copy',
                '-movflags', '+faststart',  # Enable streaming if container supports it
                '-threads', '0',
                '-y',
                output_file
            ]
        logger.info(f"Starting conversion with command: {' '.join(cmd)}")
        # Run FFmpeg with optimized settings
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            logger.error(f"FFmpeg error: {stderr.decode()}")
            return None
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            # Remove original file to save space
            if os.path.exists(input_file):
                os.remove(input_file)
            return output_file
        else:
            logger.error("Conversion failed - output file not created or empty")
            return None
    except Exception as e:
        logger.error(f"Conversion error: {str(e)}")
        return None

@Client.on_message((filters.regex(r'https?://[^\s<>"]+?\.m3u8(?:\?[^\s<>"]*)?') | filters.document) & filters.private)
async def handle_m3u8(client, message):
    """Handle M3U8 URLs or text files with streaming support"""
    try:
        # Determine output format - default to MP4 for videos, MP3 if specifically requested
        output_format = 'mp3' if message.reply_to_message and message.reply_to_message.text and '/mp3' in message.reply_to_message.text else 'mp4'

        if message.document and message.document.mime_type == "text/plain":
            status = await message.reply_text("📄 Reading and parsing file...")
            file = await message.download()
            entries = await parse_text_file(file)
            os.remove(file)

            if not entries:
                await message.reply_text("❌ No valid video entries found in file.")
                return

            total_videos = len(entries)
            total_pdfs = sum(len(entry['pdfs']) for entry in entries)

            status_msg = await message.reply_text(
                f"🔍 Found {total_videos} videos and {total_pdfs} PDFs\n"
                "⏳ Starting downloads in order..."
            )

            async with aiohttp.ClientSession() as session:
                for i, entry in enumerate(entries):
                    try:
                        title = entry['title']
                        url = entry['url']
                        clean_title = clean_filename(title)

                        await safe_edit_message(
                            status_msg,
                            f"📥 Processing {i+1}/{total_videos}\n"
                            f"Title: {clean_title}\n"
                            f"Associated PDFs: {len(entry['pdfs'])}"
                        )

                        # Download video
                        ts_file = f"temp_{message.from_user.id}_{int(datetime.now().timestamp())}.ts"
                        downloaded_file = await process_m3u8(url, ts_file, status_msg)

                        if downloaded_file and os.path.exists(downloaded_file):
                            await safe_edit_message(status_msg, f"🔄 Converting to {output_format.upper()}: {clean_title}")
                            # You may want to use convert_to_format_fast here:
                            # result_file = await convert_to_format_fast(downloaded_file, output_format)
                            # If you have an old convert_to_format, keep as is:
                            result_file = await convert_to_format_fast(downloaded_file, output_format)

                            if result_file and os.path.exists(result_file):
                                start_time = time.time()
                                try:
                                    format_emoji = "🎵" if output_format == 'mp3' else "🎥"

                                    # Use reply_video for MP4 files to enable streaming
                                    if output_format == 'mp4':
                                        await message.reply_video(
                                            video=result_file,
                                            caption=f"{format_emoji} {clean_title}",
                                            file_name=f"{clean_title}.{output_format}",
                                            supports_streaming=True,  # Enable streaming
                                            progress=progress,
                                            progress_args=(
                                                status_msg,
                                                start_time,
                                                f"📤 Uploading {output_format.upper()}: {clean_title}"
                                            )
                                        )
                                    else:
                                        # Use reply_document for MP3 and other formats
                                        await message.reply_document(
                                            result_file,
                                            caption=f"{format_emoji} {clean_title}",
                                            file_name=f"{clean_title}.{output_format}",
                                            progress=progress,
                                            progress_args=(
                                                status_msg,
                                                start_time,
                                                f"📤 Uploading {output_format.upper()}: {clean_title}"
                                            )
                                        )
                                    logger.info(f"✅ Successfully uploaded video: {clean_title}")
                                except Exception as e:
                                    logger.error(f"Error uploading video: {str(e)}")
                                    if "FLOOD_WAIT" in str(e):
                                        await handle_flood_wait(e, status_msg)
                                        continue
                                finally:
                                    if os.path.exists(result_file):
                                        os.remove(result_file)

                        # Process associated PDFs
                        for pdf_idx, pdf_entry in enumerate(entry['pdfs']):
                            pdf_title = pdf_entry['title']
                            pdf_url = pdf_entry['url']
                            pdf_clean_title = clean_filename(pdf_title)

                            await safe_edit_message(
                                status_msg,
                                f"📚 Downloading PDF {pdf_idx+1}/{len(entry['pdfs'])}\n"
                                f"Video: {clean_title}\n"
                                f"PDF: {pdf_clean_title}"
                            )

                            pdf_path = f"temp_pdf_{message.from_user.id}_{int(datetime.now().timestamp())}_{pdf_idx}.pdf"

                            if await download_pdf(session, pdf_url, pdf_path):
                                if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                                    start_time = time.time()
                                    try:
                                        await message.reply_document(
                                            pdf_path,
                                            caption=f"📚 {pdf_clean_title}\n📹 Related to: {clean_title}",
                                            file_name=f"{pdf_clean_title}.pdf",
                                            progress=progress,
                                            progress_args=(
                                                status_msg,
                                                start_time,
                                                f"📤 Uploading PDF: {pdf_clean_title}"
                                            )
                                        )
                                        logger.info(f"✅ Successfully uploaded PDF: {pdf_clean_title}")
                                    except Exception as e:
                                        logger.error(f"Error uploading PDF: {str(e)}")
                                        if "FLOOD_WAIT" in str(e):
                                            await handle_flood_wait(e, status_msg)
                                            continue
                                    finally:
                                        if os.path.exists(pdf_path):
                                            os.remove(pdf_path)
                                else:
                                    logger.error(f"PDF file is empty or doesn't exist: {pdf_path}")
                                    await message.reply_text(f"❌ PDF download failed (empty file): {pdf_clean_title}")
                            else:
                                logger.error(f"Failed to download PDF: {pdf_url}")
                                await message.reply_text(f"❌ Failed to download PDF: {pdf_clean_title}")
                    # Delay between entries
                    if i < len(entries) - 1:  # Don't delay after last entry
                        await asyncio.sleep(MIN_DELAY_BETWEEN_ENTRIES)

                    except Exception as e:
                        logger.error(f"Error processing entry {i+1}: {str(e)}")
                        await message.reply_text(f"❌ Error processing entry {i+1}: {str(e)}")
                        # Clean up any remaining files
                        for temp_file in [ts_file]:
                            if 'temp_file' in locals() and os.path.exists(temp_file):
                                os.remove(temp_file)

            await safe_edit_message(status_msg, f"✅ Processing complete!\n📹 {total_videos} videos\n📚 {total_pdfs} PDFs")

        else:  # Single URL
            status_msg = await message.reply_text("⏳ Processing single URL...")
            timestamp = int(datetime.now().timestamp())
            ts_file = f"video_{message.from_user.id}_{timestamp}.ts"

            downloaded_file = await process_m3u8(message.text, ts_file, status_msg)

            if downloaded_file and os.path.exists(downloaded_file):
                await safe_edit_message(status_msg, f"🔄 Converting to {output_format.upper()}...")

                # Fast conversion with streaming optimization
                result_file = await convert_to_format_fast(downloaded_file, output_format, enable_streaming=True)

                if result_file and os.path.exists(result_file):
                    start_time = time.time()
                    file_size = os.path.getsize(result_file)

                    try:
                        format_emoji = "🎵" if output_format == 'mp3' else "🎥"

                        # Choose upload method based on file size and format
                        if output_format in ['mp4', 'mkv'] and file_size < 3000 * 1024 * 1024:  # Less than 50MB
                            # Use video upload for better streaming support
                            with open(result_file, 'rb') as video_file:
                                await message.reply_video(
                                    video=video_file,
                                    caption=f"{format_emoji} Video - Streaming Optimized",
                                    file_name=f"video_{timestamp}.{output_format}",
                                    supports_streaming=True,
                                    width=1920,  # Set appropriate width
                                    height=1080,  # Set appropriate height
                                    duration=0,  # Let Telegram detect duration
                                    progress=progress,
                                    progress_args=(
                                        status_msg,
                                        start_time,
                                        f"📤 Uploading {output_format.upper()}..."
                                    )
                                )
                        else:
                            # Use document upload for larger files or audio
                            with open(result_file, 'rb') as doc_file:
                                await message.reply_document(
                                    document=doc_file,
                                    caption=f"{format_emoji} {'Audio' if output_format == 'mp3' else 'Video'}",
                                    file_name=f"{'audio' if output_format == 'mp3' else 'video'}_{timestamp}.{output_format}",
                                    progress=progress,
                                    progress_args=(
                                        status_msg,
                                        start_time,
                                        f"📤 Uploading {output_format.upper()}..."
                                    )
                                )

                    except Exception as e:
                        logger.error(f"Upload error: {str(e)}")
                        if "FLOOD_WAIT" in str(e):
                            await handle_flood_wait(e, status_msg)
                            # Retry with document upload after flood wait
                            try:
                                with open(result_file, 'rb') as retry_file:
                                    await message.reply_document(
                                        document=retry_file,
                                        caption=f"{format_emoji} {'Audio' if output_format == 'mp3' else 'Video'} - Retry",
                                        file_name=f"{'audio' if output_format == 'mp3' else 'video'}_{timestamp}.{output_format}",
                                        progress=progress,
                                        progress_args=(
                                            status_msg,
                                            time.time(),
                                            f"📤 Retrying upload {output_format.upper()}..."
                                        )
                                    )
                            except Exception as retry_error:
                                logger.error(f"Retry upload failed: {str(retry_error)}")
                                await message.reply_text("❌ Upload failed after retry")
                        else:
                            await message.reply_text(f"❌ Upload error: {str(e)}")
                    finally:
                        # Clean up files
                        for file_path in [result_file, downloaded_file]:
                            if os.path.exists(file_path):
                                try:
                                    os.remove(file_path)
                                except Exception as cleanup_error:
                                    logger.error(f"Cleanup error: {str(cleanup_error)}")
                else:
                    await message.reply_text("❌ Conversion failed")
            else:
                await message.reply_text("❌ Download failed")

    except Exception as e:
        logger.error(f"Handler error: {str(e)}")
        await message.reply_text(f"❌ Error: {str(e)}")

@Client.on_message(filters.command(["m3u8", "mp3", "mp4"]))
async def handle_command(client, message):
    """Handle /m3u8, /mp3, and /mp4 commands"""
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
            "[Category] Title 2:URL 2\n\n"
            "📌 **Audio extracted as high-quality MP3**\n"
            "📌 **Fast processing with optimized encoding**\n"
            "📌 **PDFs downloaded in sequential order**"
        )
    elif command == "mp4":
        await message.reply_text(
            "🎥 **M3U8 MP4 Downloader**\n\n"
            "Send me:\n"
            "• Direct M3U8 URL or\n"
            "• Text file with titles and URLs\n\n"
            "Format for text file:\n"
            "[Category] Title 1:URL 1\n"
            "PDF - [Category] Title 1\n"
            "PDF_URL 1\n\n"
            "[Category] Title 2:URL 2\n\n"
            "📌 **Videos converted to streaming-optimized MP4**\n"
            "📌 **Fast conversion with H.264 encoding**\n"
            "📌 **Supports streaming playback**"
        )
    else:  # m3u8 command
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
            "/m3u8 - Download as **MKV** (High Quality)\n"
            "/mp4 - Convert to **MP4** (Streaming Optimized)\n"
            "/mp3 - Extract audio as **MP3**\n\n"
            "📌 **Fast processing with optimized encoding**\n"
            "📌 **Streaming support for video formats**\n"
            "📌 **PDFs processed in sequential order**"
        )
