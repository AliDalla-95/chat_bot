import os
import logging
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
import psycopg2
import ocr_processor
import image_processing
import config

# Global dictionaries for pending submissions and pagination
pending_submissions = {}
user_pages = {}

# Conversation states
EMAIL, FULL_NAME = range(2)

# Initialize database connection
def connect_db():
    return psycopg2.connect(config.DATABASE_URL)

##########################
#    Database Functions  #
##########################
def user_exists(telegram_id):
    """Check if user exists in database"""
    try:
        with connect_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM users WHERE telegram_id = %s", (telegram_id,))
                return cursor.fetchone() is not None
    except psycopg2.Error as e:
        logging.error(f"Database error in user_exists: {e}")
        return False

def get_profile(telegram_id):
    """Get user profile data"""
    try:
        with connect_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT telegram_id, full_name, email, points FROM users WHERE telegram_id = %s",
                    (telegram_id,))
                return cursor.fetchone()
    except psycopg2.Error as e:
        logging.error(f"Database error in get_profile: {e}")
        return None

def link_exists(link):
    """Check if YouTube link exists in database"""
    try:
        with connect_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM links WHERE youtube_link = %s", (link,))
                return cursor.fetchone() is not None
    except psycopg2.Error as e:
        logging.error(f"Database error in link_exists: {e}")
        return False

def get_adder(telegram_id):
    """Get user's full name who added link"""
    try:
        with connect_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT full_name FROM users WHERE telegram_id = %s", (telegram_id,))
                result = cursor.fetchone()
                return result[0] if result else None
    except psycopg2.Error as e:
        logging.error(f"Database error in get_adder: {e}")
        return None

def get_allowed_links(telegram_id):
    """Get links user hasn't processed yet"""
    try:
        with connect_db() as conn:
            with conn.cursor() as cursor:
                query = """
                    SELECT l.id, l.youtube_link, l.description
                    FROM links l
                    LEFT JOIN user_link_status uls 
                        ON l.id = uls.link_id AND uls.telegram_id = %s
                    WHERE uls.processed IS NULL OR uls.processed = 0
                """
                cursor.execute(query, (telegram_id,))
                return cursor.fetchall()
    except psycopg2.Error as e:
        logging.error(f"Database error in get_allowed_links: {e}")
        return []

def mark_link_processed(telegram_id, link_id):
    """Mark link as processed for user"""
    try:
        with connect_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO user_link_status (telegram_id, link_id, processed)
                    VALUES (%s, %s, 1)
                    ON CONFLICT (telegram_id, link_id) 
                    DO UPDATE SET processed = EXCLUDED.processed
                """, (telegram_id, link_id))
                conn.commit()
    except psycopg2.Error as e:
        logging.error(f"Database error in mark_link_processed: {e}")
        conn.rollback()

def update_user_points(telegram_id, points=1):
    """Update user's points"""
    try:
        with connect_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE users 
                    SET points = points + %s
                    WHERE telegram_id = %s
                """, (points, telegram_id))
                conn.commit()
    except psycopg2.Error as e:
        logging.error(f"Database error in update_user_points: {e}")
        conn.rollback()

def get_link_description(link_id):
    """Get description for a link"""
    try:
        with connect_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT description FROM links WHERE id = %s", (link_id,))
                result = cursor.fetchone()
                return result[0] if result else None
    except psycopg2.Error as e:
        logging.error(f"Database error in get_link_description: {e}")
        return None

def is_authorized_link_adder(telegram_id):
    """Check if user is authorized to add links"""
    try:
        with connect_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM authorized_link_adders WHERE telegram_id = %s", (telegram_id,))
                return cursor.fetchone() is not None
    except psycopg2.Error as e:
        logging.error(f"Database error in is_authorized_link_adder: {e}")
        return False

##########################
#    Command Handlers    #
##########################
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show main menu keyboard"""
    keyboard = [
        ["👋 Start", "📝 Register"],
        ["📋 Profile", "🔍 View Links"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Choose a command:", reply_markup=reply_markup)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    if user_exists(user_id):
        if user_id in config.ADMIN_IDS:
            await update.message.reply_text("Welcome, Admin!\nUse Menu to see all commands.")
        elif is_authorized_link_adder(user_id):
            await update.message.reply_text("Welcome, friend!\nUse Menu to see all commands.")
        else:
            await update.message.reply_text("Welcome! \nUse Menu to see available commands.")
        await show_menu(update, context)
    elif not user_exists(user_id):
        await update.message.reply_text("Welcome to the YouTube Points Bot!\nUse Menu to start.")
        await register(update, context)


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start registration process"""
    user_id = update.effective_user.id
    if user_exists(user_id):
        await update.message.reply_text("You are already registered!")
        return ConversationHandler.END
    await update.message.reply_text("Please enter your email:")
    return EMAIL

async def process_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process email input"""
    email = update.message.text.strip()
    if '@' not in email or '.' not in email:
        await update.message.reply_text("❌ Invalid email format! Please try again.")
        return EMAIL
    
    context.user_data['email'] = email
    await update.message.reply_text("Please enter your full name:")
    return FULL_NAME

async def process_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process full name input and complete registration"""
    full_name = update.message.text.strip()
    user_id = update.effective_user.id
    email = context.user_data.get('email')

    if not full_name:
        await update.message.reply_text("❌ Full name cannot be empty! Please try again.")
        return FULL_NAME

    try:
        with connect_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO users (telegram_id, full_name, email) VALUES (%s, %s, %s)",
                    (user_id, full_name, email)
                )
                conn.commit()
        await update.message.reply_text("✅ Registration successful!\nUse /menu to start.")
    except psycopg2.Error as e:
        await update.message.reply_text(f"❌ Registration failed: {e}\nPlease try again.")
    finally:
        context.user_data.clear()
    return ConversationHandler.END

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user profile"""
    user_id = update.effective_user.id
    profile = get_profile(user_id)
    if profile:
        _, full_name, email, points = profile
        profile_text = (
            f"📋 Profile Information:\n"
            f"👤 Name: {full_name}\n"
            f"📧 Email: {email}\n"
            f"⭐ Points: {points}"
        )
        await update.message.reply_text(profile_text)
    else:
        await update.message.reply_text("❌ You're not registered! Use /register.")

async def view_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available links"""
    user_id = update.effective_user.id
    if not user_exists(user_id):
        await update.message.reply_text("❌ Please register first using /register")
        return
    
    user_pages[user_id] = 0
    await send_links_page(update.effective_chat.id, user_id, 0, context)

##########################
#    Callback Handlers   #
##########################
async def handle_submit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle image submission callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    try:
        link_id = int(query.data.split("_")[1])
        description = get_link_description(link_id)
        
        if not description:
            await query.message.reply_text("❌ Error: Link description not found.")
            return
        
        pending_submissions[user_id] = (link_id, description)
        await query.message.reply_text("📸 Please upload your image for verification.")
    except (IndexError, ValueError) as e:
        await query.message.reply_text("❌ Invalid link data.")

async def navigate_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pagination callbacks"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    try:
        new_page = int(query.data.split("_")[1])
        await send_links_page(query.message.chat_id, user_id, new_page, context)
        await query.message.delete()
    except (IndexError, ValueError) as e:
        await query.message.reply_text("❌ Invalid page navigation.")

##########################
#    Message Handlers    #
##########################
async def handle_text_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle main menu text commands"""
    text = update.message.text
    if text == "👋 Start":
        await start(update, context)
    elif text == "📝 Register":
        await register(update, context)
    elif text == "📋 Profile":
        await profile_command(update, context)
    elif text == "🔍 View Links":
        await view_links(update, context)
    else:
        await update.message.reply_text("❌ I don't understand that command.")

async def process_image_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle image uploads for verification"""
    user_id = update.effective_user.id
    if user_id not in pending_submissions:
        await update.message.reply_text("❌ No active submission! Use /viewlinks first.")
        return

    link_id, required_channel = pending_submissions[user_id]
    try:
        # Download image
        photo_file = await update.message.photo[-1].get_file()
        image_path = f"temp_{user_id}_{link_id}.jpg"
        await photo_file.download_to_drive(image_path)
        
        await update.message.reply_text("🔍 Verifying image...")
        
        # Perform verification checks
        verification_passed = False
        if ocr_processor.check_text_in_image(image_path, required_channel):
            verification_passed = True
        elif image_processing.check_text_in_image(image_path, required_channel):
            verification_passed = True

        if verification_passed:
            mark_link_processed(user_id, link_id)
            update_user_points(user_id)
            await update.message.reply_text(
                "✅ Verification successful! +1 point earned.\n"
                "🚫 This link is now completed For You."
            )
        else:
            await update.message.reply_text(
                "❌ Verification failed. Please try again."
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Error processing image: {e}")
    finally:
        if os.path.exists(image_path):
            os.remove(image_path)
        pending_submissions.pop(user_id, None)

##########################
#    Helper Functions    #
##########################
def get_paginated_links(user_id, page=0, per_page=5):
    """Get paginated list of links"""
    links = get_allowed_links(user_id)
    total_pages = (len(links) - 1) // per_page + 1 if links else 0
    start_idx = page * per_page
    end_idx = start_idx + per_page
    return links[start_idx:end_idx], total_pages

async def send_links_page(chat_id: int, user_id: int, page: int, context: ContextTypes.DEFAULT_TYPE):
    """Send a page of links with pagination controls"""
    links, total_pages = get_paginated_links(user_id, page)
    
    if not links:
        await context.bot.send_message(chat_id, "✅ No more links available at the moment!")
        return

    for link in links:
        link_id, yt_link, description = link
        # Escape both link and description
        safe_link = escape_markdown(yt_link)
        safe_desc = escape_markdown(description)
        
        text = f"📌 *YouTube Link:* {safe_link}\n📝 *Description:* {safe_desc}"
        keyboard = [[InlineKeyboardButton("📸 Submit Image", callback_data=f"submit_{link_id}")]]
        
        await context.bot.send_message(
            chat_id,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="MarkdownV2"
        )

    # Add pagination controls
    if total_pages > 1:
        pagination_buttons = []
        if page > 0:
            pagination_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"prev_{page-1}"))
        if page < total_pages - 1:
            pagination_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"next_{page+1}"))
        
        if pagination_buttons:
            await context.bot.send_message(
                chat_id,
                "Navigate between pages:",
                reply_markup=InlineKeyboardMarkup([pagination_buttons])
            )
            
def escape_markdown(text: str) -> str:
    """Escape all MarkdownV2 special characters"""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(['\\' + char if char in escape_chars else char for char in text])
##########################
#    Main Application    #
##########################
def main():
    """Start the bot"""
    application = ApplicationBuilder().token(config.TOKEN).build()

    # Registration conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('register', register)],
        states={
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_email)],
            FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_full_name)]
        },
        fallbacks=[CommandHandler('cancel', lambda u,c: ConversationHandler.END)],
    )

    # Add handlers
    handlers = [
        CommandHandler('start', start),
        CommandHandler('menu', show_menu),
        CommandHandler('profile', profile_command),
        CommandHandler('viewlinks', view_links),
        conv_handler,
        CallbackQueryHandler(handle_submit_callback, pattern="^submit_"),
        CallbackQueryHandler(navigate_links, pattern="^prev_|next_"),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_commands),
        MessageHandler(filters.PHOTO, process_image_upload)
    ]

    for handler in handlers:
        application.add_handler(handler)

    application.run_polling()

if __name__ == '__main__':
    main()