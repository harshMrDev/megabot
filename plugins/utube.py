import os
import re
import logging
import asyncio
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
import yt_dlp

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
ADMIN_USERNAME = "harshMrDev"  # Your username
START_TIME = "2025-06-18 08:35:35"  # Current UTC time

YOUTUBE_REGEX = re.compile(
    r'(https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)[\w\-\_\?&=]+)'
)

def extract_youtube_links(text):
    return YOUTUBE_REGEX.findall(text or "")

def sanitize_filename(name):
    return re.sub(r'[^a-zA-Z0-9_\-\.]', '_', name)

def make_sexy_progress_bar(downloaded, total, speed=None, eta=None, bar_length=18):
    if total == 0:
        return "🟡 Starting..."
    percent = downloaded / total
    filled_len = int(bar_length * percent)
    bar = "🟩" * filled_len + "⬜" * (bar_length - filled_len)
    percent_text = f"{percent*100:5.1f}%"
    size_text = f"{downloaded/1048576:.1f}MB / {total/1048576:.1f}MB"
    speed_text = f"🚀 {speed/1048576:.2f}MB/s" if speed else ""
    eta_text = f"⏳ {int(eta)}s left" if eta else ""
    extras = "  ".join(x for x in [speed_text, eta_text] if x)
    fun = "🔥" if speed and speed > 2*1048576 else ""
    return (
        f"*Downloading:*\n"
        f"{bar} `{percent_text}` {fun}\n"
        f"`{size_text}`\n"
        f"{extras}"
    )

# Basic command handlers
@Client.on_message(filters.command(["start"]) & filters.private)
async def start_command(client, message: Message):
    logger.info(f"Start command received from user {message.from_user.id}")
    try:
        await message.reply_text(
            f"👋 Hello {message.from_user.first_name}!\n\n"
            "🎥 I am a YouTube Downloader Bot. I can help you download videos and audio from YouTube.\n\n"
            "Available commands:\n"
            "/start - Start the bot\n"
            "/help - Show help message\n"
            "/ping - Check bot response\n"
            "/utube - Download from YouTube\n\n"
            f"🕒 Bot Started: {START_TIME}\n"
            f"👨‍💻 Admin: @{ADMIN_USERNAME}",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await message.reply_text("An error occurred. Please try again.")

@Client.on_message(filters.command(["help"]) & filters.private)
async def help_command(client, message: Message):
    logger.info(f"Help command received from user {message.from_user.id}")
    try:
        await message.reply_text(
            "📖 **Help Menu**\n\n"
            "Here are the available commands:\n\n"
            "/start - Start the bot\n"
            "/help - Show this help message\n"
            "/ping - Check if bot is working\n"
            "/utube - Start YouTube download\n\n"
            "To download from YouTube:\n"
            "1. Use /utube command\n"
            "2. Send the YouTube link\n"
            "3. Choose format (Audio/Video)\n"
            "4. For video, select quality\n\n"
            "Note: Maximum file size: 4GB",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error in help command: {e}")
        await message.reply_text("An error occurred. Please try again.")

@Client.on_message(filters.command(["ping"]) & filters.private)
async def ping_command(client, message: Message):
    logger.info(f"Ping command received from user {message.from_user.id}")
    try:
        start = datetime.now()
        ping_msg = await message.reply_text("Pinging...")
        end = datetime.now()
        duration = (end - start).microseconds / 1000
        await ping_msg.edit_text(f"Pong! 🏓\nResponse Time: {duration}ms")
    except Exception as e:
        logger.error(f"Error in ping command: {e}")
        await message.reply_text("An error occurred. Please try again.")

@Client.on_message(filters.command(["utube"]) & filters.private)
async def utube_command(client, message: Message):
    logger.info(f"YouTube command received from user {message.from_user.id}")
    try:
        await message.reply_text(
            "Please send me a YouTube link or a text file containing YouTube links.\n\n"
            "Example links:\n"
            "▫️ https://youtube.com/watch?v=...\n"
            "▫️ https://youtu.be/...\n"
            "▫️ https://youtube.com/shorts/..."
        )
    except Exception as e:
        logger.error(f"Error in utube command: {e}")
        await message.reply_text("An error occurred. Please try again.")

# Handle YouTube links
@Client.on_message(filters.regex(YOUTUBE_REGEX) & filters.private)
async def handle_youtube_link(client, message: Message):
    logger.info(f"YouTube link received from user {message.from_user.id}")
    try:
        links = extract_youtube_links(message.text)
        if not links:
            await message.reply_text("No valid YouTube links found.")
            return

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎵 Audio", callback_data="choose_audio"),
                InlineKeyboardButton("🎥 Video", callback_data="choose_video")
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="choose_cancel")]
        ])
        
        await message.reply_text(
            "Choose download format:",
            reply_markup=keyboard
        )
        user_sessions[message.from_user.id] = {"pending_links": links}
    except Exception as e:
        logger.error(f"Error handling YouTube link: {e}")
        await message.reply_text("An error occurred. Please try again.")

# Store user sessions
user_sessions = {}

# Handle callback queries
@Client.on_callback_query(filters.regex('^choose_'))
async def handle_callback(client, callback_query):
    logger.info(f"Callback received from user {callback_query.from_user.id}: {callback_query.data}")
    try:
        user_id = callback_query.from_user.id
        session = user_sessions.get(user_id, {})
        links = session.get("pending_links", [])
        data = callback_query.data

        if data == 'choose_audio':
            await callback_query.edit_message_text("🎵 Downloading audio...")
            await process_and_send(client, callback_query.message, links, 'audio')
        elif data == 'choose_video':
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("360p", callback_data="video_360"),
                    InlineKeyboardButton("480p", callback_data="video_480"),
                    InlineKeyboardButton("1080p", callback_data="video_1080")
                ],
                [InlineKeyboardButton("❌ Cancel", callback_data="choose_cancel")]
            ])
            await callback_query.edit_message_text(
                "Select video quality:",
                reply_markup=keyboard
            )
        elif data.startswith('video_'):
            quality = data.replace('video_', '')
            await callback_query.edit_message_text(f"🎥 Downloading {quality}p video...")
            await process_and_send(client, callback_query.message, links, data)
        elif data == 'choose_cancel':
            await callback_query.edit_message_text("❌ Download cancelled.")
        
        if data != 'choose_video':
            user_sessions.pop(user_id, None)
            
    except Exception as e:
        logger.error(f"Error in callback: {e}")
        await callback_query.edit_message_text("❌ An error occurred. Please try again.")

async def download_youtube(link, mode, cookies_file=None, progress_callback=None):
    logger.info(f"Starting download for {link} in mode {mode}")
    try:
        # Test tmp directory
        test_file = "/tmp/test_write.txt"
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        logger.info("Successfully tested /tmp directory write access")
    except Exception as e:
        logger.error(f"Failed to write to /tmp directory: {e}")
        raise

    def get_stream():
        outtmpl = "/tmp/%(title).60s.%(ext)s"
        ydl_opts = {
            "progress_hooks": [progress_callback] if progress_callback else [],
            "format": "best",
            "outtmpl": outtmpl,
            "noplaylist": True,
            "nocheckcertificate": True,
            "ignoreerrors": False,
            "logtostderr": False,
            "quiet": True,
            "no_warnings": True,
            "default_search": "auto",
            "source_address": "0.0.0.0"
        }

        if mode == 'audio':
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        elif mode == 'video_360':
            ydl_opts.update({
                'format': 'bestvideo[height<=360]+bestaudio/best[height<=360]/best[height<=360]',
                'merge_output_format': 'mp4',
            })
        elif mode == 'video_480':
            ydl_opts.update({
                'format': 'bestvideo[height<=480]+bestaudio/best[height<=480]/best[height<=480]',
                'merge_output_format': 'mp4',
            })
        elif mode == 'video_1080':
            ydl_opts.update({
                'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best[height<=1080]',
                'merge_output_format': 'mp4',
            })
        else:
            raise Exception("Invalid mode")

        if cookies_file and os.path.exists(cookies_file):
            ydl_opts['cookiefile'] = cookies_file

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info(f"Starting download with yt-dlp: {link}")
                info = ydl.extract_info(link, download=True)
                if mode == 'audio':
                    filename = ydl.prepare_filename(info).rsplit('.', 1)[0] + '.mp3'
                else:
                    ext = 'mp4'
                    filename = ydl.prepare_filename(info).rsplit('.', 1)[0] + f'.{ext}'
                safe_filename = '/tmp/' + sanitize_filename(os.path.basename(filename))
                if filename != safe_filename and os.path.exists(filename):
                    os.rename(filename, safe_filename)
                return safe_filename if os.path.exists(safe_filename) else filename
        except Exception as e:
            logger.error(f"Error downloading video: {str(e)}")
            raise

    return await asyncio.to_thread(get_stream)

async def process_and_send(client, message, links, mode):
    logger.info(f"Processing {len(links)} links in mode {mode}")
    cookies_file = 'cookies.txt' if os.path.exists('cookies.txt') else None
    for link in links:
        try:
            progress_msg = await message.reply(f"🎯 Processing: {link}")
            last_percent = -1

            async def edit_progress(d):
                if d['status'] == 'downloading':
                    total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                    downloaded = d.get('downloaded_bytes', 0)
                    speed = d.get('speed')
                    eta = d.get('eta')
                    if total and downloaded:
                        percent = int(100 * downloaded / total)
                        nonlocal last_percent
                        if percent != last_percent and percent % 5 == 0:  # Update every 5%
                            last_percent = percent
                            bar = make_sexy_progress_bar(downloaded, total, speed, eta)
                            try:
                                await progress_msg.edit_text(
                                    bar + f"\n[`{link}`]",
                                    parse_mode=ParseMode.MARKDOWN,
                                    disable_web_page_preview=True
                                )
                            except Exception as e:
                                logger.error(f"Error updating progress: {str(e)}")

            def progress_hook(d):
                asyncio.run_coroutine_threadsafe(edit_progress(d), client.loop)

            file_path = await download_youtube(link, mode, cookies_file, progress_hook)
            
            if not os.path.exists(file_path):
                await message.reply("❌ Download failed, file not found!")
                continue

            size = os.path.getsize(file_path)
            if size == 0:
                await message.reply("❌ File is empty. Download failed!")
                os.remove(file_path)
                continue

            if size > 4 * 1024 * 1024 * 1024:  # 4GB limit
                await message.reply("❌ File too large! Max 4GB allowed.")
                os.remove(file_path)
                continue

            await progress_msg.edit_text("✅ Uploading to Telegram...", parse_mode=ParseMode.MARKDOWN)
            await message.reply_document(file_path)
            os.remove(file_path)
            await progress_msg.delete()
            logger.info(f"Successfully processed and sent file for {link}")
        except Exception as e:
            logger.error(f"Error processing link {link}: {str(e)}")
            await message.reply(
                f"❌ Failed for {link}:\n`{str(e)}`",
                parse_mode=ParseMode.MARKDOWN
            )
