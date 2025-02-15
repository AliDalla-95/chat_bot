"""
ali
"""

import os
import sqlite3
import re
import logging
from telebot import types

import config
import database
import ocr_processor
import image_processing

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    BotCommand,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global dictionaries for pending submissions and pagination
pending_submissions = {}
user_pages = {}

##########################
#   DATABASE FUNCTIONS   #
##########################
def connect_db():
    """Returns a connection to the SQLite database."""
    return sqlite3.connect('bot_base.db')  # Adjust the path as needed

def user_exists(telegram_id):
    """Check if the user already exists in the database."""
    try:
        with connect_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            user = cursor.fetchone()
            return user is not None
    except sqlite3.Error as e:
        logger.error(f"SQLite error occurred: {e}")
        return False

def get_profile(telegram_id):
    """Retrieves a user’s profile data from the users table."""
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT telegram_id, full_name, email, points FROM users WHERE telegram_id = ?",
            (telegram_id,)
        )
        return cursor.fetchone()

def mark_link_processed(telegram_id, link_id):
    """Marks the given link as processed for the user."""
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO user_link_status (telegram_id, link_id, processed)
            VALUES (?, ?, 1)
        """, (telegram_id, link_id))
        conn.commit()

def update_user_points(telegram_id, points=1):
    """Updates the user's points in the users table."""
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET points = points + ?
            WHERE telegram_id = ?
        """, (points, telegram_id))
        conn.commit()

def get_allowed_links(telegram_id):
    """
    Returns a list of links that the user has not yet processed.
    Each returned row is a tuple: (id, youtube_link, description)
    """
    with connect_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT l.id, l.youtube_link, l.description
            FROM links l
            LEFT JOIN user_link_status uls 
                ON l.id = uls.link_id AND uls.telegram_id = ?
            WHERE uls.processed IS NULL OR uls.processed = 0
        """
        cursor.execute(query, (telegram_id,))
        return cursor.fetchall()

def get_paginated_links(user_id, page=0, per_page=5):
    """Fetches paginated YouTube links for a user."""
    links = get_allowed_links(user_id)
    total_pages = (len(links) - 1) // per_page + 1
    start = page * per_page
    end = start + per_page
    current_links = links[start:end]
    return current_links, total_pages

def get_link_description(link_id):
    """Fetches the description for a given link ID."""
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT description FROM links WHERE id = ?", (link_id,))
        result = cursor.fetchone()
        return result[0] if result else None

def is_authorized_link_adder(telegram_id):
    """Returns True if the user is authorized to add links."""
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id FROM authorized_link_adders WHERE telegram_id = ?", (telegram_id,))
        result = cursor.fetchone()
        return result is not None

##########################
#      HANDLERS          #
##########################
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Create a custom keyboard with friendly text labels and emoji
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_start = types.KeyboardButton("👋 Start")
    btn_register = types.KeyboardButton("📝 Register")
    btn_profile = types.KeyboardButton("📋 Profile")
    btn_viewlinks = types.KeyboardButton("🔍 View Links")
    
    # Add buttons to the keyboard
    markup.add(btn_start, btn_register, btn_profile, btn_viewlinks)
    
    # Send a message with the custom keyboard
    await update.message.reply_text("Choose a command:", reply_markup=markup)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    telegram_id = update.message.from_user.id
    if user_exists(telegram_id):
        if telegram_id in config.ADMIN_IDS:
            await update.message.reply_text("Welcome, Admin!\nUse Menu to see all commands.")
        elif is_authorized_link_adder(telegram_id):
            await update.message.reply_text("Welcome, friend!\nUse Menu to see all commands.")
        else:
            await update.message.reply_text("Welcome!\nUse Menu to see available commands.")
    else:
        # Set bot commands for new users
        commands = [BotCommand("start", "Start interacting with the bot"),
                    BotCommand("register", "Register your account")]
        await context.bot.set_my_commands(commands, scope=None)
        await update.message.reply_text("Welcome to the YouTube Points Bot!\nUse /menu to start.")
    await show_menu(update, context)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /register command."""
    telegram_id = update.message.from_user.id
    if user_exists(telegram_id):
        await update.message.reply_text("You are already registered!")
    else:
        await update.message.reply_text("Please enter your email, full name (comma-separated):")
        return 1  # State indicator for registration (if using ConversationHandler)

async def process_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process registration details."""
    try:
        user_data = update.message.text.split(",")
        email, full_name = map(str.strip, user_data)
        database.add_user(update.message.from_user.id, full_name, email)
        await update.message.reply_text("Registration successful!\nWelcome to the YouTube Points Bot! Use /menu to start.")
        await start(update, context)
    except Exception as e:
        await update.message.reply_text("Invalid format! Use: email, full name /register")

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /profile command."""
    profile = get_profile(update.message.from_user.id)
    if profile:
        telegram_id, full_name, email, points = profile
        profile_text = (
            f"Profile Information:\n"
            f"Telegram ID: {telegram_id}\n"
            f"Full Name: {full_name}\n"
            f"Email: {email}\n"
            f"Points: {points}"
        )
        await update.message.reply_text(profile_text)
    else:
        await update.message.reply_text("Profile not found. Please register using /register.")

async def view_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /viewlinks command."""
    telegram_id = update.message.from_user.id
    if user_exists(telegram_id):
        user_pages[telegram_id] = 0  # Start from page 0
        await send_links_page(update.message.chat.id, telegram_id, 0, context)
    else:
        await update.message.reply_text("Profile not found. Please register using /register.")

async def handle_text_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    If a user sends text matching one of the friendly button labels,
    call the corresponding command function.
    """
    text = update.message.text.strip()
    if text == "👋 Start":
        await start(update, context)
    elif text == "📝 Register":
        await register(update, context)
    elif text == "📋 Profile":
        await profile_command(update, context)
    elif text == "🔍 View Links":
        await view_links(update, context)
    else:
        await update.message.reply_text("I don't understand that command.")

async def handle_submit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Triggered when a user taps the 'Submit Image' button.
    Stores the pending link id and its description, then prompts for image upload.
    """
    query = update.callback_query
    await query.answer()
    telegram_id = query.from_user.id
    allowed = get_allowed_links(telegram_id)
    if allowed:
        try:
            link_id = int(query.data.split("_")[1])
            description = get_link_description(link_id)
            if not description:
                await query.answer("❌ Error: Link description not found.", show_alert=True)
                return
        except Exception as e:
            await query.answer("❌ Invalid link data.", show_alert=True)
            return
        pending_submissions[telegram_id] = (link_id, description)
        await query.answer("✅ Please upload your image for this link.", show_alert=True)
        await context.bot.send_message(query.message.chat.id, "📸 Upload an image now.")
    else:
        await context.bot.send_message(query.message.chat.id, "📸 Not Allowed To Upload an image now.")

async def navigate_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles pagination button clicks."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    new_page = int(query.data.split("_")[1])
    await send_links_page(query.message.chat.id, user_id, new_page, context)
    await context.bot.delete_message(query.message.chat.id, query.message.message_id)

async def process_image_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the image upload: downloads the image, processes OCR, and updates points."""
    telegram_id = update.message.from_user.id
    if telegram_id not in pending_submissions:
        await update.message.reply_text("❌ No link submission is pending. Please tap 'Submit Image' for a link first.")
        return

    link_id, required_channel = pending_submissions[telegram_id]
    photo = update.message.photo[-1]  # Highest resolution image
    file = await context.bot.get_file(photo.file_id)
    image_path = f"temp_{telegram_id}_{link_id}.jpg"
    await file.download_to_drive(image_path)

    await update.message.reply_text("🔍 Checking image")
    result = ocr_processor.check_text_in_image(image_path, required_channel)
    if result:
        mark_link_processed(telegram_id, link_id)
        update_user_points(telegram_id, 1)
        await update.message.reply_text("✅ Image verified successfully! You earned 1 point.\n🚫 This link is now blocked for you.\nPerfect Go\nUse /viewlinks to continue.")
    else:
        result = image_processing.check_text_in_image(image_path, required_channel)
        if result:
            mark_link_processed(telegram_id, link_id)
            update_user_points(telegram_id, 1)
            await update.message.reply_text("✅ Image verified successfully! You earned 1 point.\n🚫 This link is now blocked for you.\nPerfect Go\nUse /viewlinks to continue.")
        else:
            await update.message.reply_text("❌ Image verification failed.\nSorry, try again. Use /viewlinks to continue.")

    if os.path.exists(image_path):
        os.remove(image_path)
    pending_submissions.pop(telegram_id, None)

async def send_links_page(chat_id, user_id, page, context: ContextTypes.DEFAULT_TYPE):
    """Sends a specific page of YouTube links."""
    links, total_pages = get_paginated_links(user_id, page)
    if not links:
        await context.bot.send_message(chat_id, "❌ No available links at the moment.")
        return
    for link in links:
        link_id, youtube_link, description = link
        text = f"📌 **YouTube Link:** {youtube_link}\n📜 **Description:** {description}"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("📸 Submit Image", callback_data=f"submit_{link_id}")]])
        await context.bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
    if total_pages > 1:
        # Send pagination buttons
        if page > 0:
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️", callback_data=f"prev_{page-1}")]])
            await context.bot.send_message(chat_id, "Previous Page:", parse_mode="Markdown", reply_markup=markup)
        if page < total_pages - 1:
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("➡️", callback_data=f"next_{page+1}")]])
            await context.bot.send_message(chat_id, "Next Page:", parse_mode="Markdown", reply_markup=markup)

##########################
#         MAIN           #
##########################
def main():
    """Main entry point: set up the application and add handlers."""
    application = Application.builder().token(config.TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("menu", show_menu))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("viewlinks", view_links))
    
    # For registration follow-up step (you might use a ConversationHandler for a real flow)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_registration))
    
    # Unified text handler (for friendly button labels)
    application.add_handler(MessageHandler(filters.TEXT, handle_text_commands))
    
    # Callback query handlers for submission and pagination
    application.add_handler(CallbackQueryHandler(handle_submit_callback, pattern="^submit_"))
    application.add_handler(CallbackQueryHandler(navigate_links, pattern="^(prev_|next_)"))
    
    # Handler for photo uploads
    application.add_handler(MessageHandler(filters.PHOTO, process_image_upload))
    
    # Start the bot
    application.run_polling()

if __name__ == '__main__':
    main()
