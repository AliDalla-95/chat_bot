""" ali """
# Standard Library Imports
import os
import sqlite3
# Third-Party Imports
import telebot

#from telebot.types import InputMediaPhoto

# First-Party Imports (Local modules)
import image_processing

import database
import config

bot = telebot.TeleBot(config.TOKEN)

# Command to start bot
@bot.message_handler(commands=['start'])
def start(message):
    """ ali """
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
        bot.reply_to(message, "Please send your registration info in the following format:\nemail,full name,YouTube username")
        # Here, you can set up a handler to capture the next message for registration info.
        # For example:
        user_data = message.text.split(",")
        email, full_name, username = map(str.strip, user_data)
        database.add_user(message.from_user.id, username, full_name, email)
        bot.reply_to(message, "Registration successful!")
    except Exception as e:
        bot.reply_to(message, f"An error occurred: {e}")
    except:
        bot.reply_to(message, "Invalid format! Use:email,full name,YouTube username")
# Admin adding YouTube links
@bot.message_handler(commands=['addlink'])
def add_link(message):
    """ ali """
    if message.from_user.id in config.ADMIN_IDS:
        bot.send_message(message.chat.id, "Enter YouTube link and description (comma-separated):")
        bot.register_next_step_handler(message, save_link)
    else:
        bot.reply_to(message, "You are not authorized to add links.")

def save_link(message):
    """ ali """
    try:
        link, desc = map(str.strip, message.text.split(","))
        database.add_link(link, desc, message.from_user.id)
        bot.reply_to(message, "Link added successfully!")
    except:
        bot.reply_to(message, "Invalid format! Use: link, description")

# Show available YouTube links
@bot.message_handler(commands=['requests'])
def show_links(message):
    """ ali """
    links = database.get_links()
    if not links:
        bot.reply_to(message, "No links available.")
    else:
        for link, desc in links:
            bot.send_message(message.chat.id, f"🔗 {link}\n📌 {desc}")

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

# Run bot
bot.polling()
