import logging
import re
import sqlite3
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)
import os
import sys
from pathlib import Path
import psutil
from telegram.error import Conflict
import cachetools
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="googleapiclient.discovery_cache")
# ========== CONFIGURATION ==========admin
TELEGRAM_TOKEN = "7861338140:AAG3w1f7UBcwKpdYh0ipfLB3nMZM3sLasP4"
YOUTUBE_API_KEY = "AIzaSyCH0lUUlI-u1ziHsHiSl8aTC2J0nFU2l2Q"
ADMIN_TELEGRAM_ID = "6106281772"  # Get this from @userinfobot
DATABASE_NAME = "bot_base.db"

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
(
    EMAIL, 
    PHONE, 
    FULLNAME, 
    COUNTRY, 
    CHANNEL_URL
) = range(5)

# ========== MENU SYSTEM ==========
# ========== UPDATED MENU SYSTEM ==========
MAIN_MENU = [
    ["📝 Register","Start"],
    ["🔍 Input Your YouTube URL Channel"],
    ["📋 My Channels", "🗑 Delete Channel"]  # Added new menu item
]

ADMIN_MENU = [
    ["Start", "👑 Admin Panel"],
    ["🔍 Input Your YouTube URL Channel"],
    ["📋 My Channels","🗑 Delete Channel"]  # Added for admin too
]

def get_menu(user_id: int) -> ReplyKeyboardMarkup:
    """Return appropriate menu based on user status"""
    if str(user_id) == ADMIN_TELEGRAM_ID:
        return ReplyKeyboardMarkup(ADMIN_MENU, resize_keyboard=True)
    return ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)

# ========== DATABASE OPERATIONS ==========
def init_db():
    """Initialize database with proper schema"""
    conn = sqlite3.connect(DATABASE_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            user_id INTEGER PRIMARY KEY,
            telegram_id INTEGER UNIQUE,
            email TEXT,
            phone TEXT,
            fullname TEXT,
            country TEXT,
            registration_date TEXT,
            is_admin BOOLEAN DEFAULT 0,
            is_banned BOOLEAN DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            user_id INTEGER,
            adder TEXT,
            channel_id TEXT,
            channel_name TEXT,
            url TEXT,
            submission_date TEXT,
            PRIMARY KEY (user_id, channel_id),
            FOREIGN KEY (user_id) REFERENCES clients(telegram_id),
            FOREIGN KEY (user_id,url) REFERENCES likes(user_id,url) 
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS "user_likes" (
            "user_id"	INTEGER,
            "fullname"	TEXT,
            "email"	TEXT,
            "adder"	TEXT,
            "url"	TEXT,
            "channel_name"	TEXT,
        	"submission_date"	TEXT,
            "channel_likes"	INTEGER DEFAULT 1,
            PRIMARY KEY("user_id")
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            "user_id"	INTEGER,
            "channel_id"	TEXT,
            "adder"	TEXT,
            "url"	TEXT,
            "channel_name"	TEXT,
            "channel_likes"	INTEGER,
            PRIMARY KEY("user_id","url")
        )
    """)
    conn.commit()
    conn.close()

init_db()

async def is_registered(telegram_id: int) -> bool:
    """Check if user is registered"""
    conn = sqlite3.connect(DATABASE_NAME)
    c = conn.cursor()
    c.execute("SELECT 1 FROM clients WHERE telegram_id = ?", (telegram_id,))
    result = c.fetchone()
    conn.close()
    return bool(result)

# ========== CORE BOT FUNCTIONALITY ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command with dynamic menu"""
    user = update.effective_user
    menu = get_menu(user.id)
    
    # Auto-register admin if not in database
    if str(user.id) == ADMIN_TELEGRAM_ID and not await is_registered(user.id):
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute("""
            INSERT INTO clients 
            (telegram_id, email, phone, fullname, country, registration_date, is_admin)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            user.id,
            "admin@example.com",
            "+0000000000",
            "Admin User",
            "Adminland",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            1
        ))
        conn.commit()
        conn.close()
    
    await update.message.reply_text(
        f"👋 Welcome {user.first_name}!",
        reply_markup=get_menu(user.id)
    )

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process menu button selections"""
    text = update.message.text
    user = update.effective_user
    
    if text == "📝 Register":
        await handle_registration(update, context)
    elif text == "🔍 Input Your YouTube URL Channel":
        await handle_channel_verification(update, context)
    elif text == "👑 Admin Panel":
        await handle_admin_panel(update, context)
    elif text == "📋 My Channels":  # New handler
        await list_channels(update, context)
    elif text == "🔙 Main Menu":
        await show_main_menu(update, user)
    elif text == "Start":
        await start(update, context)
    else:
        await update.message.reply_text("Please use the menu buttons")

async def show_main_menu(update: Update, user):
    """Display the appropriate main menu"""
    await update.message.reply_text(
        "Main Menu:",
        reply_markup=get_menu(user.id)
    )

async def handle_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start registration process"""
    user = update.effective_user
    if await is_registered(user.id):
        await update.message.reply_text("ℹ️ You're already registered!")
        return
    await update.message.reply_text("📝 Please enter your Google email address:")
    return EMAIL

# ========== YOUTUBE CHANNEL VERIFICATION ==========
async def process_channel_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process YouTube channel URL with duplicate validation and enhanced checks"""
    try:
        user = update.effective_user
        url = update.message.text.strip()
        
        # Validate URL format first
        if not re.match(r'^(https?://)?(www\.)?youtube\.com/', url, re.IGNORECASE):
            await update.message.reply_text("❌ Invalid YouTube URL format. Please try again.")
            return ConversationHandler.END

        # YouTube API initialization with cache
        class MemoryCache:
            def __init__(self):
                self._cache = {}
            def get(self, url):
                return self._cache.get(url)
            def set(self, url, content):
                self._cache[url] = content

        youtube = build(
            "youtube",
            "v3",
            developerKey=YOUTUBE_API_KEY,
            cache=MemoryCache(),
            cache_discovery=False
        )

        # Extract channel identifier
        patterns = [
            (r'/channel/([a-zA-Z0-9_-]{24})', 'id'),  # Channel ID
            (r'/c/([a-zA-Z0-9_-]+)', 'custom'),       # Custom URL
            (r'/user/([a-zA-Z0-9_-]+)', 'user'),       # Legacy username
            (r'/@([a-zA-Z0-9_-]+)', 'handle')          # Channel handle
        ]

        channel_id = None
        channel_name = None
        identifier_type = None

        for pattern, id_type in patterns:
            match = re.search(pattern, url)
            if match:
                identifier = match.group(1)
                identifier_type = id_type
                try:
                    if id_type == 'id':
                        response = youtube.channels().list(
                            part="snippet",
                            id=identifier
                        ).execute()
                    else:
                        response = youtube.search().list(
                            part="snippet",
                            q=identifier,
                            type="channel",
                            maxResults=1
                        ).execute()

                    if response.get('items'):
                        if id_type == 'id':
                            channel = response['items'][0]
                        else:
                            channel_id = response['items'][0]['id']['channelId']
                            channel = youtube.channels().list(
                                part="snippet",
                                id=channel_id
                            ).execute()['items'][0]

                        channel_id = channel['id']
                        channel_name = channel['snippet']['title']
                        channel_name = filter_non_arabic_words(channel_name,url)
                        break

                except HttpError as e:
                    logger.error(f"YouTube API Error: {str(e)}")
                    await update.message.reply_text("❌ Error verifying channel. Please try later.")
                    return ConversationHandler.END

        if not channel_id or not channel_name:
            await update.message.reply_text("❌ Could not verify YouTube channel. Check URL and try again.")
            return ConversationHandler.END

        # Database checks
        conn = sqlite3.connect(DATABASE_NAME)
        try:
            c = conn.cursor()
            # Check existing submissions
            c.execute("""
                SELECT channel_id, description 
                FROM links 
                WHERE added_by = ? 
                AND (channel_id = ? OR description = ?)
            """, (user.id, channel_id, channel_name))
            
            existing = c.fetchone()
            if existing:
                existing_id, existing_name = existing
                message = []
                if existing_id == channel_id:
                    message.append("⚠️ You already submitted this channel ID")
                if existing_name == channel_name:
                    message.append("⚠️ You already submitted a channel with this name")
                await update.message.reply_text("\n".join(message))
                return ConversationHandler.END


            try:
                cc = conn.cursor()
                cc.execute("""
                    SELECT fullname 
                    FROM clients 
                    WHERE telegram_id = ?
                """, (
                    user.id,
                ))
                exit = cc.fetchone()
                ex = exit[0]
            except Exception as e:
                logger.error(f"Channel processing error: {str(e)}")
                await update.message.reply_text("❌ An error occurred. Please try again.")
                

            #     exit_name = exit
            #     print(f"{exit_name}")
            #     return exit_name
            # Insert new submission
            # c.execute("""
            #     INSERT INTO likes 
            #     (adder, channel_id, channel_name, url, submission_date, adder)
            #     VALUES (?, ?, ?, ?, ?, ?)
            # """, (
            #     user.id,
            #     channel_id,
            #     channel_name,
            #     url,
            #     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            #     ex,
            # ))
            c.execute("""
                INSERT INTO links 
                (added_by, youtube_link, description, channel_id, submission_date, adder)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                user.id,
                url,
                channel_name,
                channel_id,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ex,
            ))
            c.execute("""
                SELECT id 
                FROM links 
                WHERE added_by = ? and youtube_link = ? and description = ? and channel_id = ? and submission_date = ? and adder = ?
            """, (
                user.id,
                url,
                channel_name,
                channel_id,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ex,
            ))
            exit = c.fetchone()
            link_id_id = exit[0]
            c.execute("""
                INSERT OR REPLACE INTO user_link_status (telegram_id, link_id, processed)
                VALUES (?, ?, 1)
            """, (
                user.id,
                link_id_id
            ))
            conn.commit()
            await update.message.reply_text(
                f"✅ Channel registered successfully!\n\n"
                f"📛 Name: {channel_name}\n"
                f"🆔 ID: {channel_id}\n"
                f"🔗 URL: {url}"
            )
            
        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Channel processing error: {str(e)}")
        await update.message.reply_text("❌ An error occurred. Please try again.")

    return ConversationHandler.END




def filter_non_arabic_words(text, url):    
    # Regex to match only English words and spaces
    english_re = re.compile(r'[a-zA-Z\s]+')
    
    # Find all matching English parts
    matches = english_re.findall(text)
    
    # Join them into a single string and remove extra spaces
    filtered_text = ' '.join(''.join(matches).split())

    # If no English words are found, check for @ in URL
    if not filtered_text.strip():
        at_match = re.search(r'@([a-zA-Z0-9_]+)', url)
        if at_match:
            return at_match.group(1)  # Return the part after @
        else:
            return text  # Return the original text if no @ is found

    return filtered_text


# def filter_non_arabic_words(text):
#     # This regex will help us detect if a word contains any Arabic character.
#     arabic_re = re.compile(r'[\u0600-\u06FF]')
#     # arabic_re = re.compile(r'[a-zA-Z\s]+')
    
#     # Split the text into words. (This simple split may not handle punctuation perfectly.)
#     words = text.split()
#     filtered_words = []
    
#     for word in words:
#         # If the word does NOT contain any Arabic letter, keep it.
#         if not arabic_re.search(word):
#             filtered_words.append(word)
    
#     # Join the words back into a single string.
#     return ' '.join(filtered_words)


# ========== ADDITIONAL FUNCTIONS ==========
async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all submitted channels for a user"""
    user = update.effective_user
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute("""
            SELECT description, youtube_link,channel_id, submission_date 
            FROM links 
            WHERE added_by = ?
        """, (user.id,))
        channels = c.fetchall()
        conn.close()
        
        if not channels:
            await update.message.reply_text("📭 You haven't submitted any channels yet")
            return
            
        response = ["📋 Your submitted channels:"]
        for idx, (name, url, channel_id, date) in enumerate(channels, 1):
            response.append(
                f"{idx}. {name}\n"
                f"🔗 {url}\n"
                f"🆔 ID: {channel_id}\n"
                f"📅 {date}\n"
                f"--------------------------------------------\n"
            )
            
        await update.message.reply_text("\n\n".join(response))
        
    except Exception as e:
        logger.error(f"List channels error: {str(e)}")
        await update.message.reply_text("❌ Error retrieving your channels")


# ========== REGISTRATION FLOW HANDLERS ==========
async def email_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validate and store email"""
    email = update.message.text
    if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
        await update.message.reply_text("❌ Invalid email format. Try again:")
        return EMAIL
    context.user_data["email"] = email
    await update.message.reply_text("📱 Enter phone number (international format, e.g. +1234567890):")
    return PHONE

async def phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validate and store phone number"""
    phone = re.sub(r'(?!^\+)\D', '', update.message.text)
    if not re.match(r'^\+\d{8,15}$', phone):
        await update.message.reply_text("❌ Invalid phone format. Example: +1234567890")
        return PHONE
    context.user_data["phone"] = phone
    await update.message.reply_text("👤 Enter your full name:")
    return FULLNAME

async def name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store full name"""
    name = update.message.text.strip()
    if len(name) < 2 or len(name) > 100:
        await update.message.reply_text("❌ Name must be 2-100 characters")
        return FULLNAME
    context.user_data["fullname"] = name
    await update.message.reply_text("🌍 Enter your country:")
    return COUNTRY

async def country_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Complete registration"""
    country = update.message.text.strip()
    if len(country) < 2 or len(country) > 60:
        await update.message.reply_text("❌ Country name must be 2-60 characters")
        return COUNTRY
    
    user_data = context.user_data
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute("""
            INSERT INTO clients 
            (telegram_id, email, phone, fullname, country, registration_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            update.effective_user.id,
            user_data["email"],
            user_data["phone"],
            user_data["fullname"],
            country,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        await update.message.reply_text(
            "✅ Registration complete!",
            reply_markup=get_menu(update.effective_user.id)
        )
    except Exception as e:
        logger.error(f"Database error: {str(e)}")
        await update.message.reply_text("❌ Registration failed. Please try again.")
    finally:
        conn.close()
    
    return ConversationHandler.END

# ========== ADMIN FUNCTIONALITY ==========
async def handle_channel_verification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start channel verification process"""
    if not await is_registered(update.effective_user.id):
        await update.message.reply_text("❌ Please register first using /register")
        return ConversationHandler.END
    
    await update.message.reply_text("🔗 Please send your YouTube channel URL:")
    return CHANNEL_URL

async def handle_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel access control"""
    user = update.effective_user
    if str(user.id) != ADMIN_TELEGRAM_ID:
        await update.message.reply_text("🚫 Access denied!")
        return
    
    keyboard = [
        # ["📊 User Statistics", "📢 Broadcast Message"],
        ["🚫 Ban User", "🗑 Delete Channel"],  # Updated buttons
        ["🔙 Main Menu","🗑 Delete  ALL Channel"]
    ]
    await update.message.reply_text(
        "👑 Admin Panel:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# ========== IMPROVED ERROR HANDLING ==========
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and handle different error types"""
    logger.error("Exception:", exc_info=context.error)
    
    try:
        # Handle cases where update might be None
        if update and update.effective_message:
            error_message = "⚠️ An error occurred. Please try again."
            
            # Handle specific error types
            if isinstance(context.error, Conflict):
                error_message = "🔌 Bot conflict detected! Please restart the bot."
                
            await update.effective_message.reply_text(error_message)
            
    except Exception as e:
        logger.error(f"Error handler failed: {str(e)}")
        
# ========== ADMIN DELETE CHANNELS ==========
async def delete_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only channel deletion flow"""
    # user = update.effective_user
    # if str(user.id) != ADMIN_TELEGRAM_ID:
    #     await update.message.reply_text("🚫 Access denied!")
    #     return ConversationHandler.END

    await update.message.reply_text("Enter Channel URL to delete:")
    return "AWAIT_CHANNEL_URL"


async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm and delete channel"""
    url = update.message.text.strip()
    conn = sqlite3.connect(DATABASE_NAME)
    try:
        c = conn.cursor()
        c.execute("SELECT description FROM links WHERE youtube_link = ? and added_by = ?", (url,update.effective_user.id,))
        result = c.fetchone()
        
        if not result:
            await update.message.reply_text("❌ Channel not found")
            return ConversationHandler.END

        channel_name = result[0]
        c.execute("SELECT id FROM links WHERE youtube_link = ? and added_by = ?", (url, update.effective_user.id,))
        result_id = c.fetchone()
        if not result_id:
            await update.message.reply_text("❌ Channel not found")
            return ConversationHandler.END
        result_id_for_link = result_id[0]
        c.execute("DELETE FROM links WHERE youtube_link = ? and added_by = ?", (url,update.effective_user.id,))
        c.execute("DELETE FROM user_link_status WHERE link_id = ?", (result_id_for_link,))
        c.execute("DELETE FROM likes WHERE url = ? and user_id = ?", (url,update.effective_user.id,))
        conn.commit()
        await update.message.reply_text(
            f"✅ Channel deleted:\n"
            f"📛 Name: {channel_name}\n"
            f"🔗 URL: {url}"
        )
    finally:
        conn.close()
    return ConversationHandler.END

AWAIT_CHANNEL_URL_ADMIN, AWAIT_CHANNEL_ADDER_ADMIN = range(2)

async def delete_channel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only channel deletion flow: prompt for channel URL."""
    user = update.effective_user
    if str(user.id) != ADMIN_TELEGRAM_ID:
        await update.message.reply_text("🚫 Access denied!")
        return ConversationHandler.END

    await update.message.reply_text("Enter Channel URL to delete:")
    return "AWAIT_CHANNEL_URL_ADMIN"

# Step 2: Receive the Channel URL and prompt for the adder
async def receive_channel_url_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store the channel URL and prompt for the adder."""
    # Save the channel URL in user_data for later retrieval
    context.user_data["channel_url"] = update.message.text.strip()
    await update.message.reply_text("And enter the 'adder' (the user who added the channel):")
    return "AWAIT_ADDER"

# Step 3: Receive the adder and confirm deletion
async def confirm_delete_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm deletion using the stored channel URL and the provided adder."""
    adder = update.message.text.strip()  # Now this is the admin's input text, not a Message object
    url = context.user_data.get("channel_url")
    
    if not url:
        await update.message.reply_text("Channel URL not found. Aborting deletion.")
        return ConversationHandler.END

    conn = sqlite3.connect(DATABASE_NAME)
    try:
        c = conn.cursor()
        c.execute("SELECT description FROM links WHERE youtube_link = ? and adder = ?", (url, adder))
        result = c.fetchone()
        if not result:
            await update.message.reply_text("❌ Channel not found")
            return ConversationHandler.END
            
        channel_name = result[0]
        c.execute("SELECT id FROM links WHERE youtube_link = ? and adder = ?", (url, adder,))
        result_id = c.fetchone()
        if not result_id:
            await update.message.reply_text("❌ Channel not found")
            return ConversationHandler.END
        result_id_for_link = result_id[0]
        c.execute("DELETE FROM user_link_status WHERE link_id = ?", (result_id_for_link,))
        c.execute("DELETE FROM likes WHERE url = ? and adder = ?", (url,adder,))
        c.execute("DELETE FROM links WHERE youtube_link = ? and adder = ?", (url, adder))
        conn.commit()
        await update.message.reply_text(
            f"✅ Channel deleted:\n"
            f"📛 Name: {channel_name}\n"
            f"🔗 URL: {url}"
        )
    finally:
        conn.close()

    return ConversationHandler.END


# ========== BAN USER FUNCTIONALITY ==========
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ban a user from using the bot"""
    admin = update.effective_user
    if str(admin.id) != ADMIN_TELEGRAM_ID:
        await update.message.reply_text("🚫 Access denied!")
        return

    # Extract user ID from message (could be reply or direct input)
    target_id = None
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
    elif context.args and len(context.args) > 0:
        try:
            target_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Usage: /ban <user_id> or reply to user's message")
            return
    else:
        await update.message.reply_text("Usage: /ban <user_id> or reply to user's message")
        return

    conn = sqlite3.connect(DATABASE_NAME)
    try:
        c = conn.cursor()
        # Ban user
        c.execute("""
            UPDATE clients 
            SET is_banned = 1 
            WHERE telegram_id = ?
        """, (target_id,))
        
        if c.rowcount == 0:
            await update.message.reply_text("❌ User not found in database")
            return
            
        conn.commit()
        await update.message.reply_text(f"✅ User {target_id} has been banned")
        
        # Notify banned user if possible
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="🚫 Your access to this bot has been revoked"
            )
        except Exception as e:
            logger.error(f"Ban notification failed: {str(e)}")
            
    finally:
        conn.close()

def main() -> None:
    """Configure and start the bot with comprehensive error handling"""
    pid_file = Path("bot.pid")
    logger = logging.getLogger(__name__)

    try:
        # ========== PID FILE HANDLING ==========
        # Check for existing instances with validation
        if pid_file.exists():
            try:
                content = pid_file.read_text().strip()
                if not content:
                    raise ValueError("Empty PID file")
                
                old_pid = int(content)
                if psutil.pid_exists(old_pid):
                    print("⛔ Another bot instance is already running!")
                    print("❗ Use 'kill %d' or restart your computer" % old_pid)
                    sys.exit(1)
                    
            except (ValueError, psutil.NoSuchProcess) as e:
                logger.warning(f"Cleaning invalid PID file: {str(e)}")
                pid_file.unlink(missing_ok=True)
            except psutil.Error as e:
                logger.error(f"PID check failed: {str(e)}")
                sys.exit(1)

        # Write new PID file with atomic write
        try:
            with pid_file.open("w") as f:
                f.write(str(os.getpid()))
                os.fsync(f.fileno())
        except IOError as e:
            logger.critical(f"Failed to write PID file: {str(e)}")
            sys.exit(1)

        # ========== BOT INITIALIZATION ==========
        application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

        # ========== HANDLER CONFIGURATION ==========
        # Admin conversation handler
        admin_conv = ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex(r"^🗑 Delete Channel"), delete_channel),
                MessageHandler(filters.Regex(r"^🗑 Delete  ALL Channel$"), delete_channel_admin),
                MessageHandler(filters.Regex(r"^🚫 Ban User$"), ban_user)
            ],
            states={
                "AWAIT_CHANNEL_URL": [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_delete)],
                "AWAIT_CHANNEL_URL_ADMIN": [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_channel_url_admin)],
                "AWAIT_ADDER": [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_delete_admin)],
            },
            fallbacks=[CommandHandler("cancel", lambda u,c: ConversationHandler.END)],
            map_to_parent={ConversationHandler.END: ConversationHandler.END}
        )

        # Main conversation handler
        conv_handler = ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex(r"^📝 Register$"), handle_registration),
                MessageHandler(filters.Regex(r"^🔍 Input Your YouTube URL Channel$"), handle_channel_verification),
                MessageHandler(filters.Regex(r"^🗑 Delete Channel$"), delete_channel),
            ],
            states={
                EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, email_handler)],
                PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_handler)],
                FULLNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_handler)],
                COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, country_handler)],
                CHANNEL_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_channel_url)],
                "AWAIT_CHANNEL_URL": [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_delete)],
            },
            fallbacks=[CommandHandler("cancel", lambda u,c: ConversationHandler.END)]
        )

        # ========== HANDLER REGISTRATION ==========
        handlers = [
            CommandHandler("start", start),
            conv_handler,
            admin_conv,
            MessageHandler(filters.Regex(r"^👑 Admin Panel$"), handle_admin_panel),
            MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler),
            CommandHandler("ban", ban_user),
            CommandHandler("mychannels", list_channels)
        ]

        # ========== BAN CHECK WRAPPER ==========
        async def is_banned(telegram_id: int) -> bool:
            """Check if user is banned with DB connection handling"""
            try:
                conn = sqlite3.connect(DATABASE_NAME)
                c = conn.cursor()
                c.execute("SELECT is_banned FROM clients WHERE telegram_id = ?", (telegram_id,))
                result = c.fetchone()
                return bool(result and result[0] == 1)
            except sqlite3.Error as e:
                logger.error(f"Ban check failed: {str(e)}")
                return False
            finally:
                conn.close()

        def wrap_handler(handler):
            """Safe handler wrapper with ban checking"""
            if not hasattr(handler, 'callback'):
                return handler
                
            original_callback = handler.callback
            async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
                try:
                    # Skip if no valid user context
                    if not update or not update.effective_user:
                        return await original_callback(update, context)
                        
                    # Check ban status
                    if await is_banned(update.effective_user.id):
                        await update.message.reply_text("🚫 Your access has been revoked")
                        return ConversationHandler.END
                        
                    return await original_callback(update, context)
                except Exception as e:
                    logger.error(f"Handler error: {str(e)}")
                    return ConversationHandler.END
                    
            handler.callback = wrapped
            return handler

        # Apply ban checks to all handlers
        wrapped_handlers = [wrap_handler(h) for h in handlers]
        application.add_handlers(wrapped_handlers)

        # ========== ERROR HANDLING ==========
        application.add_error_handler(error_handler)

        # ========== BOT STARTUP ==========
        logger.info("Starting bot...")
        application.run_polling(
            poll_interval=2,
            timeout=30,
            drop_pending_updates=True
        )

    except Conflict as e:
        logger.critical(f"Bot conflict: {str(e)}")
        print("""
        🔌 Connection conflict detected!
        Possible solutions:
        1. Wait 10 seconds before restarting
        2. Check for other running instances
        3. Verify your bot token is unique
        """)
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}", exc_info=True)
    finally:
        # ========== CLEANUP ==========
        try:
            pid_file.unlink(missing_ok=True)
            logger.info("Cleanup completed")
        except Exception as e:
            logger.error(f"Cleanup failed: {str(e)}")

        # Ensure database connections are closed
        sqlite3.connect(DATABASE_NAME).close()

if __name__ == "__main__":
    main()