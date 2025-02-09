""" ali """
# Standard Library Imports
import os
import sqlite3
# Third-Party Imports
import telebot

from telebot import types
from telebot.types import InputMediaPhoto
# First-Party Imports (Local modules)
import image_processing

import database
import config

bot = telebot.TeleBot(config.TOKEN)

# @bot.message_handler(commands=['menu'])
# def show_menu(message):
#     # Create a custom keyboard
#     markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    
#     # Create buttons for your commands
#     btn_start = types.KeyboardButton("/start")
#     btn_register = types.KeyboardButton("/register")
#     btn_requests = types.KeyboardButton("/requests")
#     btn_help = types.KeyboardButton("/help")
#     btn_profile = types.KeyboardButton("/profile")
    
#     # Add the buttons to the keyboard layout
#     markup.add(btn_start, btn_register, btn_requests, btn_help, btn_profile)
    
#     # Send a message with the custom keyboard
#     bot.send_message(message.chat.id, "Choose a command:", reply_markup=markup)

# # Optionally, you can also remove the keyboard later if needed:
# @bot.message_handler(commands=['hide'])
# def hide_menu(message):
    # hide_markup = types.ReplyKeyboardRemove()
    # bot.send_message(message.chat.id, "Keyboard hidden", reply_markup=hide_markup)


@bot.message_handler(commands=['start'])
def start(message):
    """ ali """
    if user_exists(message.from_user.id):    
        if message.from_user.id in config.ADMIN_IDS:
            # Define commands for admins
            admin_commands = [
                    types.BotCommand("start", "Start interacting with the bot"),
                    types.BotCommand("register", "Register your account"),
                    types.BotCommand("requests", "Show YouTube links"),
                    types.BotCommand("help", "Get help with commands"),
                    types.BotCommand("profile", "Show Your profile"),
                    types.BotCommand("addlink", "addlink and descriptions"),           
            ]
            bot.set_my_commands(admin_commands, scope=types.BotCommandScopeChat(message.chat.id))
            bot.reply_to(message, "Welcome, Admin! Use /menu to see all commands.")
        else:
        # Define commands for non-admin users
            user_commands = [
                types.BotCommand("start", "Start interacting with the bot"),
                types.BotCommand("register", "Register your account"),
                types.BotCommand("requests", "Show YouTube links"),
                types.BotCommand("help", "Get help with commands"),
                types.BotCommand("profile", "Show Your profile"),
            ]
            bot.set_my_commands(user_commands, scope=types.BotCommandScopeChat(message.chat.id))
            bot.reply_to(message, "Welcome! Use /menu to see available commands.")
    else:
        bot.reply_to(message, "Welcome to the YouTube Points Bot! Use /register to start.")
    
# Register users
@bot.message_handler(commands=['register'])
def register(message):
    """ ali """
    try:
        if user_exists(message.from_user.id):
            bot.reply_to(message, "You are already registered!")
        else:
            bot.send_message(message.chat.id,
                            "Please enter your email,full name,YouTube username(comma-separated):")
            bot.register_next_step_handler(message, save_registration)
    except Exception as e:
        bot.reply_to(message, f"An error occurred: {e}")
            
def connect_db():
    """Returns a connection to the SQLite database."""
    return sqlite3.connect('database.db')  # Adjust the path as needed

def user_exists(telegram_id):
    """Check if the user already exists in the database."""
    try:
        with connect_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            user = cursor.fetchone()  # If a row is returned, the user exists
            return user is not None
    except sqlite3.Error as e:
        print(f"SQLite error occurred: {e}")
        return False

def save_registration(message):
    
    """Checks registration status and prompts for registration if needed."""
    # Debugging output: print the split result
    # print(f"User Data Split: {user_data}")  # Debugging line
    # Debugging output: print the stripped values
    # print(f"id: {message.from_user.id}, Email: {email}, Full Name: {full_name}, Username: {username}")  # Debugging line
    # if isinstance(email, str):
    #     print(f"Valid Telegram ID: {email}")
    # else:
    #     print("Invalid Telegram ID!")
    try:
        # Here, you can set up a handler to capture the next message for registration info.
        # For example:
        user_data = message.text.split(",")
        email, full_name, username = map(str.strip, user_data)
        database.add_user(message.from_user.id, username, full_name, email)
        bot.reply_to(message, "Registration successful!")
    except:
        bot.reply_to(message, "Invalid format! Use:email,full name,YouTube username /register")
                
# Show available YouTube links
@bot.message_handler(commands=['requests'])
def show_links(message):
    """ ali """
    profile = get_profile(message.from_user.id)
    if profile:
        links = database.get_links()
        if not links:
            bot.reply_to(message, "No links available.")
        else:
            for link, desc in links:
                bot.send_message(message.chat.id, f"🔗 {link}\n📌 {desc}")
    else:
        bot.reply_to(message, "Please register using /register.")

# Handle image uploads
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    """ ali """
    bot.reply_to(message, "Send the YouTube link you're linking this image to:")
    bot.register_next_step_handler(message, lambda msg: save_image(msg, message.photo[-1].file_id))

def save_image(message, file_id):
    """ ali """
    link = message.text
    file_info = bot.get_file(file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    # Save image locally
    file_path = f"data/images/{file_id}.jpg"
    with open(file_path, 'wb') as new_file:
        new_file.write(downloaded_file)

    # Process image
    if image_processing.check_text_in_image(file_path, link):
        database.add_points(message.from_user.id)
        bot.reply_to(message, "✅ Image verified! You earned a point.")
    else:
        bot.reply_to(message, "❌ Image does not meet criteria.")

def get_profile(telegram_id):
    """Retrieves a user’s profile data from the profiles table."""
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT telegram_id, username, full_name, email, points FROM users WHERE telegram_id = ?",
            (telegram_id,)
        )
        return cursor.fetchone()


@bot.message_handler(commands=['help'])
def help_command(message):
    """Displays a list of available commands and their descriptions."""
    help_text = (
        "Here are the available commands:\n"
        "/start - Begin interaction or re-check registration\n"
        "/profile - View your profile information\n"
        "/help - Show this help message\n"
        "/register - Show this registration\n"
        "/requests - Show this links\n"
        # Add any additional commands here
    )
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['profile'])
def profile_command(message):
    """Displays the user's profile information."""
    profile = get_profile(message.from_user.id)
    if profile:
        telegram_id, username, full_name, email, points = profile
        profile_text = (
            f"Profile Information:\n"
            f"Telegram ID: {telegram_id}\n"
            f"Username: {username}\n"
            f"Full Name: {full_name}\n"
            f"Email: {email}\n"
            f"Points: {points}"
        )
        bot.reply_to(message, profile_text)
    else:
        bot.reply_to(message, "Profile not found. Please register using /register.")


def add_link_to_db(link, description, admin_id):
    """Inserts a new link with description into the links table."""
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO links (youtube_link, description, added_by)
            VALUES (?, ?, ?)
        """, (link, description, admin_id))
        conn.commit()

@bot.message_handler(commands=['addlink'])
def add_link_command(message):
    """
    This command lets an admin add a new link.
    It first checks if the user is authorized, then asks for link and description.
    """
    # Check if the sender is an admin
    if message.from_user.id not in config.ADMIN_IDS:
        bot.reply_to(message, "Sorry, you are not authorized to use this command.")
        return

    # Ask the admin for the link and description in a single message
    bot.reply_to(message, "Please send the link and description separated by a comma:\n\nlink, description")
    # The next message will be processed by the next handler function
    bot.register_next_step_handler(message, process_add_link)

def process_add_link(message):
    """Processes the admin's reply to add the link and description."""
    try:
        # Split the input. Using maxsplit=1 allows the description to contain commas.
        parts = message.text.split(",", 1)
        if len(parts) != 2:
            raise ValueError("Invalid format. Please ensure you separate the link and description with a comma.")
        
        # Remove extra spaces
        link = parts[0].strip()
        description = parts[1].strip()

        # Insert the link into the database
        add_link_to_db(link, description, message.from_user.id)
        bot.reply_to(message, "Link added successfully!")
    except Exception as e:
        bot.reply_to(message, f"Error adding link. Ensure the format is correct: link, description. ({e})")


# # Admin adding YouTube links
# @bot.message_handler(commands=['addlink'])
# def add_link(message):
#     """ ali """
#     if message.from_user.id in config.ADMIN_IDS:
#         bot.send_message(message.chat.id, "Enter YouTube link and description (comma-separated):")
#         bot.register_next_step_handler(message, save_link)
#     else:
#         bot.reply_to(message, "You are not authorized to add links.")

# def save_link(message):
#     """ ali """
#     try:
#         link, desc = map(str.strip, message.text.split(","))
#         database.add_link(link, desc, message.from_user.id)
#         bot.reply_to(message, "Link added successfully!")
#     except:
#         bot.reply_to(message, "Invalid format! Use: link, description")




# Run bot
bot.polling()
