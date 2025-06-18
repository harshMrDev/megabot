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
ADMIN_USERNAME = "harshMrDev"
START_TIME = "2025-06-18 08:24:41"

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

# Simple test command to verify bot responsiveness
@Client.on_message(filters.command("ping"))
async def ping_command(client, message: Message):
    logger.info(f"Received ping command from user {message.from_user.id}")
    try:
        start_time = datetime.now()
        msg = await message.reply_text("Pinging...")
        end_time = datetime.now()
        await msg.edit_text(f"Pong! 🏓\nResponse time: {(end_time - start_time).microseconds / 1000}ms")
        logger.info("Successfully sent pong response")
    except Exception as e:
        logger.error(f"Error in ping command: {str(e)}")

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

# Store user sessions
user_sessions = {}

@Client.on_message(filters.command("start"))
async def start(client, message: Message):
    logger.info(f"Received start command from user {message.from_user.id}")
    try:
        await message.reply(
            "🎉 *YouTube Downloader Bot*\n\n"
            "Send a YouTube link (or a .txt file with links).\n"
            "I'll ask for Audio/Video and, if video, ask for quality.\n"
            "Files up to 4GB supported.\n\n"
            f"Bot Started at: `{START_TIME}`\n"
            f"Admin: @{ADMIN_USERNAME}",
            parse_mode=ParseMode.MARKDOWN
        )
        logger.info("Successfully sent start message")
    except Exception as e:
        logger.error(f"Error in start command: {str(e)}")

@Client.on_message(filters.command("help"))
async def help_command(client, message: Message):
    logger.info(f"Received help command from user {message.from_user.id}")
    try:
        await message.reply(
            "📖 *Help Menu*\n\n"
            "1. Send a YouTube link or a .txt file with links\n"
            "2. Choose Audio or Video format\n"
            "3. For video, select quality (360p/480p/1080p)\n"
            "4. Wait for processing and download\n\n"
            "Commands:\n"
            "/start - Start the bot\n"
            "/help - Show this help message\n"
            "/ping - Check bot's response time\n\n"
            "Note: Files up to 4GB are supported\n"
            f"Admin: @{ADMIN_USERNAME}",
            parse_mode=ParseMode.MARKDOWN
        )
        logger.info("Successfully sent help message")
    except Exception as e:
        logger.error(f"Error in help command: {str(e)}")

@Client.on_message(filters.text | filters.document)
async def handle_message(client, message: Message):
    logger.info(f"Received message from user {message.from_user.id}")
    try:
        links = []
        if message.document and message.document.mime_type == "text/plain":
            file = await client.download_media(message.document)
            with open(file, "r") as f:
                for line in f:
                    links += extract_youtube_links(line.strip())
            os.remove(file)
            logger.info(f"Processed text file with {len(links)} links")
        elif message.text:
            links = extract_youtube_links(message.text)
            logger.info(f"Extracted {len(links)} links from text message")

        if not links:
            await message.reply("No YouTube links found.")
            return

        user_sessions[message.from_user.id] = {"pending_links": links}
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎵 Audio", callback_data="choose_audio"),
             InlineKeyboardButton("📺 Video", callback_data="choose_video")],
            [InlineKeyboardButton("❌ Cancel", callback_data="choose_cancel")]
        ])
        await message.reply("Choose format:", reply_markup=keyboard)
        logger.info(f"Sent format selection to user {message.from_user.id}")
    except Exception as e:
        logger.error(f"Error handling message: {str(e)}")
        await message.reply("Sorry, an error occurred while processing your request.")

@Client.on_callback_query()
async def inline_callback(client, callback_query):
    logger.info(f"Received callback query from user {callback_query.from_user.id}: {callback_query.data}")
    try:
        user_id = callback_query.from_user.id
        session = user_sessions.get(user_id, {})
        links = session.get("pending_links", [])
        data = callback_query.data

        if data == 'choose_audio':
            await callback_query.edit_message_text("Downloading audio...")
            await process_and_send(client, callback_query.message, links, 'audio')
            user_sessions.pop(user_id, None)
        elif data == 'choose_video':
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📺 360p", callback_data='video_360'),
                 InlineKeyboardButton("📺 480p", callback_data='video_480'),
                 InlineKeyboardButton("📺 1080p", callback_data='video_1080')],
                [InlineKeyboardButton("❌ Cancel", callback_data='choose_cancel')]
            ])
            await callback_query.edit_message_text("Choose video quality:", reply_markup=keyboard)
            session["awaiting_quality"] = True
        elif data in ['video_360', 'video_480', 'video_1080']:
            quality_label = data.replace("video_", "")
            await callback_query.edit_message_text(f"Downloading {quality_label}p video...")
            await process_and_send(client, callback_query.message, links, data)
            user_sessions.pop(user_id, None)
        elif data == 'choose_cancel':
            await callback_query.edit_message_text("Operation cancelled.")
            user_sessions.pop(user_id, None)
        else:
            await callback_query.edit_message_text("Unknown action.")
        logger.info(f"Successfully processed callback {data} for user {user_id}")
    except Exception as e:
        logger.error(f"Error in callback: {str(e)}")
        await callback_query.edit_message_text("Sorry, an error occurred.")

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
