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
START_TIME = "2025-06-18 17:45:08"
ADMIN_USERNAME = "harshMrDev"
MAX_CONCURRENT_DOWNLOADS = 10
CHUNK_SIZE = 1024 * 1024

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def parse_text_file(file_path):
    """Parse text file to extract titles and URLs"""
    titles_dict = {}
    current_title = None
    
    try:
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as file:
            async for line in file:
                line = line.strip()
                if not line:  # Skip empty lines
                    continue
                    
                if line.startswith(('http://', 'https://')):
                    if current_title:
                        titles_dict[line] = current_title
                        current_title = None
                else:
                    current_title = line

        logger.info(f"Parsed {len(titles_dict)} titles from file")
        return titles_dict
    except Exception as e:
        logger.error(f"Error parsing file: {str(e)}")
        return {}

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

# [Previous download functions remain the same]

@Client.on_message((filters.regex(r'https?://[^\s<>"]+?\.m3u8(?:\?[^\s<>"]*)?') | filters.document) & filters.private)
async def handle_m3u8(client, message):
    """Handle M3U8 URLs or text files"""
    try:
        output_format = 'mp3' if message.reply_to_message and message.reply_to_message.text and '/mp3' in message.reply_to_message.text else 'mp4'
        
        links = []
        titles = {}
        
        if message.document and message.document.mime_type == "text/plain":
            status = await message.reply_text("📄 Reading file...")
            file = await message.download()
            # Parse titles using the async function
            titles = await parse_text_file(file)
            # Extract URLs
            async with aiofiles.open(file, 'r', encoding='utf-8') as f:
                content = await f.read()
                links.extend(re.findall(r'https?://[^\s<>"]+?\.m3u8(?:\?[^\s<>"]*)?', content))
            os.remove(file)
            
            logger.info(f"Found {len(titles)} titles for {len(links)} links")
            
        elif message.text:
            links = [message.text.strip()]
        
        if not links:
            await message.reply_text("❌ No valid M3U8 URLs found")
            return

        emoji = "🎵" if output_format == 'mp3' else "🎥"
        status_msg = await message.reply_text(
            f"🔍 Found {len(links)} URL(s)\n"
            "⏳ Processing..."
        )

        for idx, url in enumerate(links, 1):
            try:
                # Get title or generate from URL
                title = titles.get(url) or url.split('/')[-1].split('.')[0]
                clean_title = clean_filename(title)
                
                logger.info(f"Processing {idx}/{len(links)}: {clean_title}")
                
                base_output = f"media_{message.from_user.id}_{int(datetime.now().timestamp())}"
                output_file = f"{base_output}.ts"
                
                await status_msg.edit_text(
                    f"📥 Processing: {clean_title}\n"
                    f"Progress: {idx}/{len(links)}"
                )

                # Download and convert
                ts_file = await process_m3u8(url, output_file, status_msg)
                
                if ts_file and os.path.exists(ts_file):
                    await status_msg.edit_text(f"🔄 Converting: {clean_title}")
                    result_file = await convert_to_format(ts_file, output_format)
                    
                    if result_file and os.path.exists(result_file):
                        file_size = os.path.getsize(result_file)
                        
                        if file_size == 0:
                            await message.reply_text(f"❌ {clean_title} is empty")
                        elif file_size > 2000 * 1024 * 1024:
                            await message.reply_text(f"❌ {clean_title} too large (>2GB)")
                        else:
                            await status_msg.edit_text(f"📤 Uploading: {clean_title}")
                            
                            caption = f"{emoji} {clean_title}"
                            
                            # Send with proper filename
                            await message.reply_document(
                                result_file,
                                caption=caption,
                                file_name=f"{clean_title}.{output_format}"
                            )
                        
                        os.remove(result_file)
                    else:
                        await message.reply_text(f"❌ Conversion failed: {clean_title}")
                else:
                    await message.reply_text(f"❌ Download failed: {clean_title}")

            except Exception as e:
                logger.error(f"Error processing {output_format} {idx}: {str(e)}")
                await message.reply_text(f"❌ Error processing: {clean_title}\n`{str(e)}`")
                for f in [output_file, ts_file, result_file]:
                    if 'f' in locals() and os.path.exists(f):
                        os.remove(f)

        await status_msg.edit_text(f"✅ All {output_format.upper()} files processed!")

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
