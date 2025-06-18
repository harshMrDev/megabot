import os
import re
import m3u8
import aiohttp
import aiofiles
import asyncio
import logging
import subprocess
from datetime import datetime
from urllib.parse import urljoin
from pyrogram import Client, filters
from pyrogram.types import Message

# Constants
START_TIME = "2025-06-18 17:40:32"
ADMIN_USERNAME = "harshMrDev"
MAX_CONCURRENT_DOWNLOADS = 10
CHUNK_SIZE = 1024 * 1024

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
                output_file
            ]
        else:  # mp4
            cmd = [
                'ffmpeg', '-i', input_file,
                '-c', 'copy',
                output_file
            ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            os.remove(input_file)  # Remove input file
            return output_file
        return None
    except Exception as e:
        logger.error(f"Conversion error: {str(e)}")
        return None

# [Previous helper functions remain the same]

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
            "URL 1\n"
            "Title 2\n"
            "URL 2\n\n"
            "I will extract audio and send MP3 files!"
        )
    else:
        await message.reply_text(
            "📥 **M3U8 Video Downloader**\n\n"
            "Send me:\n"
            "• Direct M3U8 URL or\n"
            "• Text file with titles and URLs\n\n"
            "Format for text file:\n"
            "Title 1\n"
            "URL 1\n"
            "Title 2\n"
            "URL 2\n\n"
            "Commands:\n"
            "/m3u8 - Download as MP4\n"
            "/mp3 - Extract audio as MP3"
        )

@Client.on_message((filters.regex(r'https?://[^\s<>"]+?\.m3u8(?:\?[^\s<>"]*)?') | filters.document) & filters.private)
async def handle_m3u8(client, message):
    """Handle M3U8 URLs or text files"""
    try:
        # Determine output format based on command context
        output_format = 'mp3' if message.reply_to_message and message.reply_to_message.text and '/mp3' in message.reply_to_message.text else 'mp4'
        
        links = []
        titles = {}
        
        if message.document and message.document.mime_type == "text/plain":
            file = await message.download()
            titles = await parse_titles_from_file(file)
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
                links.extend(re.findall(r'https?://[^\s<>"]+?\.m3u8(?:\?[^\s<>"]*)?', content))
            os.remove(file)
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
                base_output = f"media_{message.from_user.id}_{int(datetime.now().timestamp())}"
                output_file = f"{base_output}.ts"
                
                title = titles.get(url, f"{'Audio' if output_format == 'mp3' else 'Video'} {idx}")
                
                await status_msg.edit_text(
                    f"📥 Processing: {title}\n"
                    f"Progress: {idx}/{len(links)}"
                )

                # Download as TS first
                ts_file = await process_m3u8(url, output_file, status_msg)
                
                if ts_file and os.path.exists(ts_file):
                    # Convert to desired format
                    await status_msg.edit_text(f"🔄 Converting: {title}")
                    result_file = await convert_to_format(ts_file, output_format)
                    
                    if result_file and os.path.exists(result_file):
                        file_size = os.path.getsize(result_file)
                        
                        if file_size == 0:
                            await message.reply_text(f"❌ {title} is empty")
                        elif file_size > 2000 * 1024 * 1024:  # 2GB limit
                            await message.reply_text(f"❌ {title} too large (>2GB)")
                        else:
                            await status_msg.edit_text(f"📤 Uploading: {title}")
                            
                            caption = f"{emoji} {title}"
                            
                            await message.reply_document(
                                result_file,
                                caption=caption,
                                file_name=f"{title}.{output_format}"
                            )
                        
                        os.remove(result_file)
                    else:
                        await message.reply_text(f"❌ Conversion failed: {title}")
                else:
                    await message.reply_text(f"❌ Download failed: {title}")

            except Exception as e:
                logger.error(f"Error processing {output_format} {idx}: {str(e)}")
                await message.reply_text(f"❌ Error processing: {title}\n`{str(e)}`")
                for f in [output_file, ts_file, result_file]:
                    if 'f' in locals() and os.path.exists(f):
                        os.remove(f)

        await status_msg.edit_text(f"✅ All {output_format.upper()} files processed!")

    except Exception as e:
        await message.reply_text(f"❌ Error: `{str(e)}`")
        logger.error(f"Handler error: {str(e)}")
