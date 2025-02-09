""" ali """
# Standard Library Imports
import os

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
    bot.send_message(message.chat.id,
                     "Please enter your id, email, full name, and YouTube username (comma-separated):")
    bot.register_next_step_handler(message, save_registration)

def save_registration(message):
    """ ali """
    try:
        email, full_name, username = map(str.strip, message.text.split(","))
        database.add_user(message.from_user.id, username, full_name, email)
        bot.reply_to(message, "Registration successful!")
    except:
        bot.reply_to(message, "Invalid format! Use: email, full name, YouTube username")

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
