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

import cachetools
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="googleapiclient.discovery_cache")
# ========== CONFIGURATION ==========
TELEGRAM_TOKEN = "7861338140:AAG3w1f7UBcwKpdYh0ipfLB3nMZM3sLasP4"
YOUTUBE_API_KEY = "AIzaSyCH0lUUlI-u1ziHsHiSl8aTC2J0nFU2l2Q"
ADMIN_TELEGRAM_ID = "6106281772"  # Get this from @userinfobot
DATABASE_NAME = "client.db"

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
    ["📝 Register", "🔍 Input Your YouTube URL Channel"],
    ["📋 My Channels"]  # Added new menu item
]

ADMIN_MENU = [
    ["🔍 Input Your YouTube URL Channel", "👑 Admin Panel"],
    ["📋 My Channels"]  # Added for admin too
]

def get_menu(user_id: int) -> ReplyKeyboardMarkup:
    """Return appropriate menu based on user status"""
    if str(user_id) == ADMIN_TELEGRAM_ID:
        return ReplyKeyboardMarkup(ADMIN_MENU, resize_keyboard=True)
    return ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)

# ========== DATABASE OPERATIONS ==========
# ========== DATABASE SCHEMA UPDATE ==========
def init_db():
    """Initialize database with proper schema"""
    conn = sqlite3.connect(DATABASE_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            telegram_id INTEGER UNIQUE,
            email TEXT,
            phone TEXT,
            fullname TEXT,
            country TEXT,
            registration_date TEXT,
            is_admin BOOLEAN DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            user_id INTEGER,
            channel_id TEXT,
            channel_name TEXT,
            url TEXT,
            submission_date TEXT,
            PRIMARY KEY (user_id, channel_id),
            FOREIGN KEY (user_id) REFERENCES users(telegram_id)
        )
    """)
    conn.commit()
    conn.close()

init_db()

async def is_registered(telegram_id: int) -> bool:
    """Check if user is registered"""
    conn = sqlite3.connect(DATABASE_NAME)
    c = conn.cursor()
    c.execute("SELECT 1 FROM users WHERE telegram_id = ?", (telegram_id,))
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
            INSERT INTO users 
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
                SELECT channel_id, channel_name 
                FROM channels 
                WHERE user_id = ? 
                AND (channel_id = ? OR channel_name = ?)
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

            # Insert new submission
            c.execute("""
                INSERT INTO channels 
                (user_id, channel_id, channel_name, url, submission_date)
                VALUES (?, ?, ?, ?, ?)
            """, (
                user.id,
                channel_id,
                channel_name,
                url,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
# ========== ADDITIONAL FUNCTIONS ==========
async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all submitted channels for a user"""
    user = update.effective_user
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute("""
            SELECT channel_name, url, submission_date 
            FROM channels 
            WHERE user_id = ?
        """, (user.id,))
        channels = c.fetchall()
        conn.close()
        
        if not channels:
            await update.message.reply_text("📭 You haven't submitted any channels yet")
            return
            
        response = ["📋 Your submitted channels:"]
        for idx, (name, url, date) in enumerate(channels, 1):
            response.append(
                f"{idx}. {name}\n"
                f"   🔗 {url}\n"
                f"   📅 {date}"
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
            INSERT INTO users 
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
        ["📊 User Statistics", "📢 Broadcast Message"],
        ["🚫 Ban User", "🔙 Main Menu"]
    ]
    await update.message.reply_text(
        "👑 Admin Panel:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# ========== ERROR HANDLING ==========
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and notify user"""
    logger.error(msg="Exception:", exc_info=context.error)
    if update.effective_message:
        await update.message.reply_text("⚠️ An error occurred. Please try again.")

# ========== APPLICATION SETUP ==========
def main() -> None:
    """Configure and start the bot"""
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^📝 Register$"), handle_registration),
            MessageHandler(filters.Regex(r"^🔍 Input Your YouTube URL Channel$"), handle_channel_verification)
        ],
        states={
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, email_handler)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_handler)],
            FULLNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_handler)],
            COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, country_handler)],
            CHANNEL_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_channel_url)]
        },
        fallbacks=[],
    )

    # Add handlers
    application.add_handlers([
        CommandHandler("start", start),
        conv_handler,
        MessageHandler(filters.Regex(r"^👑 Admin Panel$"), handle_admin_panel),
        MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler)
    ])
    application.add_handler(CommandHandler("mychannels", list_channels))
    application.add_error_handler(error_handler)
    application.run_polling()

if __name__ == "__main__":
    main()