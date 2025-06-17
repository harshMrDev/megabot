import os
import importlib
import textwrap
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Create the main Pyrogram Client
app = Client(
    "unified_modular_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# Dynamically load plugin modules and register their handlers
def load_plugins():
    plugins_dir = "plugins"
    loaded = []
    for fname in os.listdir(plugins_dir):
        if fname.endswith(".py") and fname != "__init__.py":
            mod_name = f"{plugins_dir}.{fname[:-3]}"
            mod = importlib.import_module(mod_name)
            if hasattr(mod, "add_handlers"):
                mod.add_handlers(app)
                loaded.append(fname[:-3])
    return loaded

PLUGINS = load_plugins()

# Pretty menu for /start, /help, and main UI
BOT_TITLE = "🤖 Ultimate Downloader Bot"
BOT_DESC = (
    "Welcome! I'm your all-in-one media assistant.\n\n"
    "• Download from YouTube, m3u8 streams, and more (plugins!).\n"
    "• Fast, reliable, with beautiful progress and clear instructions.\n"
    "• Split large files, merge helpers, and blazing-fast streaming.\n"
    "• Just use the menu or / commands!"
)

def get_main_menu():
    # Dynamically list available plugins and their commands
    buttons = []
    if "utube" in PLUGINS:
        buttons.append(
            [InlineKeyboardButton("🎬 YouTube Download", switch_inline_query_current_chat="/utube ")]
        )
    if "m3u8" in PLUGINS:
        buttons.append(
            [InlineKeyboardButton("🟢 m3u8 Video Download", switch_inline_query_current_chat="/m3u8 ")]
        )
    # Add more buttons for future plugins
    buttons.append(
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    )
    return InlineKeyboardMarkup(buttons)

@app.on_message(filters.command("start"))
async def start(client, message: Message):
    await message.reply(
        f"{BOT_TITLE}\n\n{BOT_DESC}",
        reply_markup=get_main_menu(),
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_message(filters.command("help"))
async def help_command(client, message: Message):
    plugin_help = {
        "utube": (
            "🎬 <b>YouTube Downloader</b>\n"
            "<code>/utube &lt;youtube link&gt;</code>\n"
            "Download audio or video from YouTube. Choose quality, progress bars, file splitting for big videos.\n"
        ),
        "m3u8": (
            "🟢 <b>m3u8 Stream Downloader</b>\n"
            "<code>/m3u8 &lt;stream-url&gt;</code>\n"
            "Download and repackage m3u8 (HLS) video streams for Telegram.\n"
        ),
    }
    text = f"<b>{BOT_TITLE}</b>\n\n"
    text += "I'm a modular downloader bot. Here are my powers:\n\n"
    for pname in PLUGINS:
        text += plugin_help.get(pname, f"• <code>/{pname}</code> (see plugin for usage)\n")
    text += "\n<b>How to use:</b> Send a command, follow the prompts. All downloads are private and fast!\n"
    text += "You can reply to a message with a command for convenience.\n"

    await message.reply(
        text,
        reply_markup=get_main_menu(),
        parse_mode=ParseMode.HTML
    )

@app.on_callback_query(filters.regex("help"))
async def inline_help(client, callback_query):
    await help_command(client, callback_query.message)
    await callback_query.answer()

@app.on_message(filters.command(""))
async def unknown_command(client, message: Message):
    # For unknown commands, show menu
    await message.reply(
        "❓ Unknown command. Please use the menu or /help.",
        reply_markup=get_main_menu()
    )

if __name__ == "__main__":
    print("Starting Ultimate Downloader Bot")
    app.run()