""" ali """
# Standard Library Imports
import os
import sqlite3
# Third-Party Imports
import telebot
import database
from telebot import types
from telebot.types import InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton

# First-Party Imports (Local modules)
import image_processing

import database
import config

bot = telebot.TeleBot(config.TOKEN)
pending_submissions = {}
user_pages = {}
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
                    # types.BotCommand("requests", "Show YouTube links"),
                    types.BotCommand("help", "Get help with commands"),
                    types.BotCommand("profile", "Show Your profile"),
                    types.BotCommand("addlink", "addlink and descriptions"),
                    types.BotCommand("listlinks", "show list links for deleting"),
                    types.BotCommand("viewlinks", "Show Your links"),
                    types.BotCommand("addlinkadder", "add friends"),
                    types.BotCommand("deletelinkadder", "delete select adder by his name."),
                    types.BotCommand("showlinkadders", "show all of friends who adders"),                                                    
            ]
            bot.set_my_commands(admin_commands, scope=types.BotCommandScopeChat(message.chat.id))
            bot.reply_to(message, "Welcome, Admin! Use /menu to see all commands.")
        elif is_authorized_link_adder(message.from_user.id):
            # Define commands for admins
            admin_commands = [
                    types.BotCommand("start", "Start interacting with the bot"),
                    types.BotCommand("register", "Register your account"),
                    # types.BotCommand("requests", "Show YouTube links"),
                    types.BotCommand("help", "Get help with commands"),
                    types.BotCommand("profile", "Show Your profile"),
                    types.BotCommand("addlink", "addlink and descriptions"),
                    types.BotCommand("listlinks", "show list links for deleting"),
                    types.BotCommand("viewlinks", "Show Your links"),             
            ]
            bot.set_my_commands(admin_commands, scope=types.BotCommandScopeChat(message.chat.id))
            bot.reply_to(message, "Welcome, friend! Use /menu to see all commands.")
        else:
        # Define commands for non-admin users
            user_commands = [
                types.BotCommand("start", "Start interacting with the bot"),
                types.BotCommand("register", "Register your account"),
                # types.BotCommand("requests", "Show YouTube links"),
                types.BotCommand("help", "Get help with commands"),
                types.BotCommand("profile", "Show Your profile"),
                types.BotCommand("viewlinks", "Show Your links"),
            ]
            bot.set_my_commands(user_commands, scope=types.BotCommandScopeChat(message.chat.id))
            bot.reply_to(message, "Welcome! Use /menu to see available commands.")
    else:
                # Define commands for non-admin users
        user_commands = [
            types.BotCommand("start", "Start interacting with the bot"),
            types.BotCommand("register", "Register your account"),
        ]
        bot.set_my_commands(user_commands, scope=types.BotCommandScopeChat(message.chat.id))
        bot.reply_to(message, "Welcome to the YouTube Points Bot! Use /menu to start.")
    
    
# Register users
@bot.message_handler(commands=['register'])
def register(message):
    """ ali """
    try:
        if user_exists(message.from_user.id):
            bot.reply_to(message, "You are already registered!")
        else:
            bot.send_message(message.chat.id,
                            "Please enter your email,full name(comma-separated):")
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
        email, full_name = map(str.strip, user_data)
        database.add_user(message.from_user.id, full_name, email)
        bot.reply_to(message, "Registration successful!\nWelcome to the YouTube Points Bot! Use /menu to start.")
        bot.register_next_step_handler(message, start)
    except:
        bot.reply_to(message, "Invalid format! Use:email,full name /register")
                
# Show available YouTube links
# @bot.message_handler(commands=['requests'])
# def show_links(message):
#     """ ali """
#     profile = get_profile(message.from_user.id)
#     if profile:
#         links = database.get_links()
#         if not links:
#             bot.reply_to(message, "No links available.")
#         else:
#             for link, desc in links:
#                 bot.send_message(message.chat.id, f"🔗 {link}\n📌 {desc}")
#     else:
#         bot.reply_to(message, "Please register using /register.")

# Handle image uploads
# @bot.message_handler(content_types=['photo'])
# def handle_photo(message):
#     """ ali """
#     bot.reply_to(message, "Send the YouTube link you're linking this image to:")
#     bot.register_next_step_handler(message, lambda msg: save_image(msg, message.photo[-1].file_id))

# def save_image(message, file_id):
#     """ ali """
#     link = message.text
#     file_info = bot.get_file(file_id)
#     downloaded_file = bot.download_file(file_info.file_path)

#     # Save image locally
#     file_path = f"data/images/{file_id}.jpg"
#     with open(file_path, 'wb') as new_file:
#         new_file.write(downloaded_file)

#     # Process image
#     if image_processing.check_text_in_image(file_path, link):
#         database.add_points(message.from_user.id)
#         bot.reply_to(message, "✅ Image verified! You earned a point.")
#     else:
#         bot.reply_to(message, "❌ Image does not meet criteria.")

def get_profile(telegram_id):
    """Retrieves a user’s profile data from the profiles table."""
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT telegram_id, full_name, email, points FROM users WHERE telegram_id = ?",
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
        # "/requests - Show this links\n"
        # Add any additional commands here
    )
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['profile'])
def profile_command(message):
    """Displays the user's profile information."""
    profile = get_profile(message.from_user.id)
    if profile:
        telegram_id, full_name, email, points = profile
        profile_text = (
            f"Profile Information:\n"
            f"Telegram ID: {telegram_id}\n"
            f"Full Name: {full_name}\n"
            f"Email: {email}\n"
            f"Points: {points}"
        )
        bot.reply_to(message, profile_text)
    else:
        bot.reply_to(message, "Profile not found. Please register using /register.")

def link_exists(link):
    """Check if the user already exists in the database."""
    try:
        with connect_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM links WHERE youtube_link = ?", (link,))
            user = cursor.fetchone()  # If a row is returned, the user exists
            return user is not None
    except sqlite3.Error as e:
        print(f"SQLite error occurred: {e}")
        return False

def add_link_to_db(link, description, admin_id):
    """Inserts a new link with description into the links table."""
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO links (youtube_link, description, added_by)
            VALUES (?, ?, ?)
        """, (link, description, admin_id))
        conn.commit()

# @bot.message_handler(commands=['addlink'])
# def add_link_command(message):
#     """
#     This command lets an admin add a new link.
#     It first checks if the user is authorized, then asks for link and description.
#     """
#     # Check if the sender is an admin
#     if message.from_user.id not in config.ADMIN_IDS:
#         bot.reply_to(message, "Sorry, you are not authorized to use this command.")
#         return

#     # Ask the admin for the link and description in a single message
#     bot.reply_to(message, "Please send the link and description separated by a comma:\n\nlink, description")
#     # The next message will be processed by the next handler function
#     bot.register_next_step_handler(message, process_add_link)

# def process_add_link(message):
#     """Processes the admin's reply to add the link and description."""
#     try:
#         parts = message.text.split(",", 1)
#         if len(parts) != 2:
#             raise ValueError("Invalid format. Please ensure you separate the link and description with a comma.")
            
#         # Remove extra spaces
#         link = parts[0].strip()
#         if link_exists(link):
#             bot.reply_to(message, "the link is already selected!")
#         else:
#             # Split the input. Using maxsplit=1 allows the description to contain commas.
#             parts = message.text.split(",", 1)
#             if len(parts) != 2:
#                 raise ValueError("Invalid format. Please ensure you separate the link and description with a comma.")
            
#             # Remove extra spaces
#             link = parts[0].strip()
#             description = parts[1].strip()

#             # Insert the link into the database
#             add_link_to_db(link, description, message.from_user.id)
#             bot.reply_to(message, "Link added successfully!")
#     except Exception as e:
#         bot.reply_to(message, f"Error adding link. Ensure the format is correct: link, description. ({e})")


@bot.message_handler(commands=['addlink'])
def add_link(message):
    """Admin command to add a YouTube link with a description."""
    user_id = message.from_user.id
    if message.from_user.id not in config.ADMIN_IDS and not is_authorized_link_adder(user_id):
        bot.reply_to(message, "❌ You are not authorized to add links.")
        return

    bot.reply_to(message, "📌 Send the link followed by the description (Example: `https://youtube.com/example This is a description`)")
    bot.register_next_step_handler(message, process_add_link)

def process_add_link(message):
    telegram_id=message.from_user.id
    """Processes admin input and stores the YouTube link with description."""
    if message.from_user.id not in config.ADMIN_IDS and not is_authorized_link_adder(telegram_id):
        bot.reply_to(message, "❌ You are not authorized to add links.")
        return

    text = message.text.strip()
    if not text:
        bot.reply_to(message, "❌ Invalid format. Please enter a YouTube link followed by a description.")
        return

    # Separate the YouTube link and description
    parts = text.split(" ", 1)  # Split only once
    if len(parts) < 2:
        bot.reply_to(message, "❌ Invalid format. Please provide a description after the link.")
        return
    link = parts[0].strip()
    if link_exists(link):
            bot.reply_to(message, "the link is already selected!")
    else:
        youtube_link, description = parts[0], parts[1]  # Keep spaces in description
        user = message.from_user.id
        # Save to database
        with connect_db() as conn:
            adder = get_adder(user)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO links (youtube_link, description, added_by, adder) VALUES (?, ?, ?, ?)", 
                        (youtube_link, description, telegram_id, adder[0]))
            conn.commit()

        bot.reply_to(message, f"✅ Link added successfully!\n📌 **Link:** {youtube_link}\n📝 **Description:** {description}")
def get_adder(user):
    """ ali """
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT full_name FROM users WHERE telegram_id = ?",(user,))
        return cursor.fetchone()


def delete_link_from_db(link_id):
    """
    Deletes the link with the given link_id from the links table.
    
    Args:
        link_id (int): The ID of the link to delete.
    
    Returns:
        bool: True if a link was deleted, False otherwise.
    """
    try:
        with connect_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM links WHERE id = ?", (link_id,))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error deleting link: {e}")
        return False


@bot.message_handler(commands=['listlinks'])
def list_links(message):
    """
    Lists all links with an inline 'Delete' button next to each.
    Only accessible by admins.
    """
    user_id=message.from_user.id
    # Check if the user is an admin
    if message.from_user.id not in config.ADMIN_IDS and not is_authorized_link_adder(user_id) :
        bot.reply_to(message, "Sorry, you're not authorized to perform this action.")
        return

    # Query the links from the database
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, youtube_link, description FROM links")
        links = cursor.fetchall()

    if not links:
        bot.reply_to(message, "No links available.")
        return

    # For each link, send a message with an inline keyboard button for deletion
    for link in links:
        link_id, youtube_link, description = link
        text = f"ID: {link_id}\nLink: {youtube_link}\nDescription: {description}"
        markup = types.InlineKeyboardMarkup()
        # Set the callback_data to include the link id (e.g., "delete_3")
        delete_button = types.InlineKeyboardButton("Delete", callback_data=f"delete_{link_id}")
        markup.add(delete_button)
        bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_"))
def callback_delete_link(call):
    """
    Processes the inline 'Delete' button click.
    Deletes the link with the provided ID if the user is an admin.
    """
    user_id=call.from_user.id
    # Ensure the user is an admin
    if call.from_user.id not in config.ADMIN_IDS and not is_authorized_link_adder(user_id):
        bot.answer_callback_query(call.id, "You are not authorized.", show_alert=True)
        return

    try:
        # Extract the link ID from the callback data (e.g., "delete_3")
        link_id = int(call.data.split("_")[1])
    except (IndexError, ValueError):
        bot.answer_callback_query(call.id, "Invalid callback data.", show_alert=True)
        return

    # Attempt to delete the link
    if delete_link_from_db(link_id):
        bot.answer_callback_query(call.id, "Link deleted successfully!")
        # Optionally, update the message to show that the link has been deleted.
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="This link has been deleted."
        )
    else:
        bot.answer_callback_query(call.id, "Failed to delete link. It may have already been removed.", show_alert=True)





def get_allowed_links(telegram_id):
    """
    Returns a list of links that the user has not yet processed.
    Each returned row is a tuple: (id, youtube_link, description)
    """
    with connect_db() as conn:
        cursor = conn.cursor()
        # We use a LEFT JOIN to filter out links that have been processed (processed = 1)
        query = """
            SELECT l.id, l.youtube_link, l.description
            FROM links l
            LEFT JOIN user_link_status uls 
                ON l.id = uls.link_id AND uls.telegram_id = ?
            WHERE uls.processed IS NULL OR uls.processed = 0
        """
        cursor.execute(query, (telegram_id,))
        return cursor.fetchall()

def mark_link_processed(telegram_id, link_id):
    """Marks the given link as processed for the user."""
    with connect_db() as conn:
        cursor = conn.cursor()
        # Use INSERT OR REPLACE to update (or create) the record.
        cursor.execute("""
            INSERT OR REPLACE INTO user_link_status (telegram_id, link_id, processed)
            VALUES (?, ?, 1)
        """, (telegram_id, link_id))
        conn.commit()

def update_user_points(telegram_id, points=1):
    """Updates the user's points in the profiles table."""
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET points = points + ?
            WHERE telegram_id = ?
        """, (points, telegram_id))
        conn.commit()

# -----------------------
# BOT COMMAND HANDLERS
# -----------------------

def get_link_description(link_id):
    """Fetches the description for a given link ID."""
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT description FROM links WHERE id = ?", (link_id,))
        result = cursor.fetchone()
        return result[0] if result else None

# -----------------------
# BOT COMMAND HANDLERS
# -----------------------

@bot.message_handler(commands=['viewlinks'])
def view_links(message):
    """
    Shows the user only the links that they are allowed to see
    (i.e. those they haven't processed successfully yet).
    Each link is shown with an inline button to submit an image.
    """
    """Shows paginated YouTube links to the user."""
    try:
        if user_exists(message.from_user.id):
            user_id = message.from_user.id
            user_pages[user_id] = 0  # Start from page 0
            send_links_page(message.chat.id, user_id, 0)
        else:
            bot.reply_to(message, "Profile not found. Please register using /register.")

            bot.register_next_step_handler(message, register)
    except Exception as e:
        bot.reply_to(message, f"An error occurred: {e}")

            
        # telegram_id = message.from_user.id
        # allowed_links = get_allowed_links(telegram_id)
        # if not allowed_links:
        #     bot.reply_to(message, "No links available for you at this time.")
        #     return

        # for link in allowed_links:
        #     link_id, youtube_link, description = link
        #     text = f"📌 **YouTube Link:** {youtube_link}\n📜 **Description:** {description}"
        #     markup = types.InlineKeyboardMarkup()
        #     submit_btn = types.InlineKeyboardButton("📸 Submit Image", callback_data=f"submit_{link_id}")
        #     markup.add(submit_btn)
        #     bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")
        
@bot.callback_query_handler(func=lambda call: call.data.startswith("submit_"))
def handle_submit_callback(call):
    """
    Triggered when a user taps the 'Submit Image' button.
    Stores the pending link id and its description for that user,
    then prompts them to upload an image.
    """
    telegram_id = call.from_user.id
    try:
        link_id = int(call.data.split("_")[1])
        description = get_link_description(link_id)  # Get the ChannelName from description
        if not description:
            bot.answer_callback_query(call.id, "❌ Error: Link description not found.")
            return
    except (IndexError, ValueError):
        bot.answer_callback_query(call.id, "❌ Invalid link data.")
        return

    # Store the pending submission with the description
    pending_submissions[telegram_id] = (link_id, description)
    bot.answer_callback_query(call.id, "✅ Please upload your image for this link.")
    bot.send_message(call.message.chat.id, "📸 Upload an image now.")

@bot.message_handler(content_types=['photo'])
def process_image_upload(message):
    """
    Handles the image upload. Checks if there is a pending submission for the user.
    Downloads the image, runs the image processing function, and if successful,
    marks the link as processed for that user and updates their points.
    """
    telegram_id = message.from_user.id
    if telegram_id not in pending_submissions:
        bot.reply_to(message, "❌ No link submission is pending. Please tap 'Submit Image' for a link first.")
        return

    link_id, required_channel = pending_submissions[telegram_id]
    photo = message.photo[-1]  # Get the highest resolution image.
    file_info = bot.get_file(photo.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    image_path = f"temp_{telegram_id}_{link_id}.jpg"
    with open(image_path, "wb") as f:
        f.write(downloaded_file)

    # --- IMAGE PROCESSING ---
    # bot.reply_to(message, f"🔍 Checking if image contains: **{required_channel}** and 'Subscribed'...")
    bot.reply_to(message, f"🔍 Checking image")

    # Call your image processing function from image_processing.py.
    result = image_processing.check_text_in_image(image_path, required_channel)

    if result:
        mark_link_processed(telegram_id, link_id)
        update_user_points(telegram_id, 1)
        bot.reply_to(message, f"✅ Image verified successfully! You earned 1 point.\n🚫 This link is now blocked for you.")
        bot.reply_to(message, "Perfect Go\nUse /viewlinks to continue.")
    else:
        bot.reply_to(message, "❌ Image verification failed. Ensure the required text is present.")
        bot.reply_to(message, "Sorry Not Bad Ok\nTry Again /viewlinks to Win.")

    # Clean up: remove the temporary image file and pending submission record.
    if os.path.exists(image_path):
        os.remove(image_path)
    pending_submissions.pop(telegram_id, None)

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



def get_paginated_links(user_id, page=0, per_page=5):
    """Fetches paginated YouTube links for a user."""
    links = get_allowed_links(user_id)  # Fetch all links
    total_pages = (len(links) - 1) // per_page + 1  # Calculate total pages
    start = page * per_page
    end = start + per_page
    current_links = links[start:end]  # Slice 5 links for the current page

    return current_links, total_pages


def send_links_page(chat_id, user_id, page):
    """Sends a specific page of YouTube links."""
    links, total_pages = get_paginated_links(user_id, page)

    # Create message text
    text = "**🔗 YouTube Links (Page {}/{})**\n\n".format(page + 1, total_pages)
    for link in links:
        link_id, youtube_link, description = link
        text = f"📌 **YouTube Link:** {youtube_link}\n📜 **Description:** {description}"
        markup = types.InlineKeyboardMarkup()
        submit_btn = types.InlineKeyboardButton("📸 Submit Image", callback_data=f"submit_{link_id}")
        markup.add(submit_btn)
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
    # Inline Keyboard for Navigation
    markup = InlineKeyboardMarkup()

    if page > 0:
        markup.add(InlineKeyboardButton("⬅️ Previous", callback_data=f"prev_{page-1}"))
    
    if page < total_pages - 1:
        markup.add(InlineKeyboardButton("Next ➡️", callback_data=f"next_{page+1}"))

    bot.send_message(chat_id, "More Or Less ..............", parse_mode="Markdown", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("prev_") or call.data.startswith("next_"))
def navigate_links(call):
    """Handles pagination button clicks."""
    user_id = call.from_user.id
    new_page = int(call.data.split("_")[1])  # Extract page number
    send_links_page(call.message.chat.id, user_id, new_page)
    bot.delete_message(call.message.chat.id, call.message.message_id)  # Delete old message




def is_authorized_link_adder(telegram_id):
    """Returns True if the user is authorized to add links."""
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id FROM authorized_link_adders WHERE telegram_id = ?", (telegram_id,))
        result = cursor.fetchone()
        return result is not None



# -----------------------
# ADMIN COMMANDS FOR AUTHORIZING LINK ADDERS
# -----------------------

@bot.message_handler(commands=['addlinkadder'])
def add_link_adder(message):
    """
    Admin command to authorize a user to add links.
    Only admins (from ADMIN_IDS) can use this command.
    """
    if message.from_user.id not in config.ADMIN_IDS:
        bot.reply_to(message, "❌ You are not authorized to use this command.")
        return

    msg = ("Please send the details of the user to authorize in the following format:\n"
           "`telegram_id,full_name,email`")
    bot.reply_to(message, msg, parse_mode="Markdown")
    bot.register_next_step_handler(message, process_add_link_adder)

def process_add_link_adder(message):
    """Processes admin input to add an authorized link adder."""
    try:
        parts = message.text.split(",", 2)
        if len(parts) < 3:
            bot.reply_to(message, "❌ Invalid format. Please provide: telegram_id, full_name, email")
            return

        telegram_id = int(parts[0].strip())
        full_name = parts[1].strip()
        email = parts[2].strip()

        with connect_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO authorized_link_adders (telegram_id, full_name, email, added_by)
                VALUES (?, ?, ?, ?)
            """, (telegram_id, full_name, email, message.from_user.id))
            conn.commit()

        bot.reply_to(message, f"✅ User {full_name} (ID: {telegram_id}) has been authorized to add links.")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")
        
        
        

@bot.message_handler(commands=['deletelinkadder'])
def delete_link_adder(message):
    """
    Admin command to remove a user from the authorized link adders list.
    Only admins (from ADMIN_IDS) can use this command.
    """
    # Check if the sender is an admin.
    if message.from_user.id not in config.ADMIN_IDS:
        bot.reply_to(message, "❌ You are not authorized to use this command.")
        return

    # Prompt admin for the Telegram ID of the user to remove.
    msg = ("Please send the Name of the user you want to remove "
           "from the authorized link adders list.")
    bot.reply_to(message, msg)
    # Register next step handler to process the admin's reply.
    bot.register_next_step_handler(message, process_delete_link_adder)

def process_delete_link_adder(message):
    """
    Processes the admin's reply to remove an authorized link adder.
    Expects a message containing only the Telegram ID (as a number).
    """
    try:
        user = message.from_user.id
        adder = get_adder(user)
        with connect_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM authorized_link_adders WHERE full_name = ?",
                (adder[0],)
            )
            conn.commit()
            if cursor.rowcount > 0:
                bot.reply_to(message, f"✅ User with Name {adder} has been removed from the authorized link adders list.")
            else:
                bot.reply_to(message, "❌ No user with that Name was found in the authorized link adders list.")
    except Exception as e:
        bot.reply_to(message, f"❌ An error occurred: {e}")



@bot.message_handler(commands=['showlinkadders'])
def show_link_adders(message):
    """
    Admin command to display the list of authorized link adders.
    Only users in ADMIN_IDS can use this command.
    """
    # Check if the sender is an admin.
    if message.from_user.id not in config.ADMIN_IDS:
        bot.reply_to(message, "❌ You are not authorized to use this command.")
        return

    # Connect to the database and fetch authorized link adders.
    try:
        with connect_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT telegram_id, full_name, email FROM authorized_link_adders")
            adders = cursor.fetchall()
    except Exception as e:
        bot.reply_to(message, f"❌ An error occurred while fetching data: {e}")
        return

    # Check if any authorized adders were found.
    if not adders:
        bot.reply_to(message, "No authorized link adders found.")
        return

    # Build a formatted message with the list of adders.
    text = "📋 **Authorized Link Adders:**\n\n"
    for adder in adders:
        # adder is a tuple in the form (telegram_id, full_name, username, email)
        telegram_id, full_name, email = adder
        text += f"• ID: `{telegram_id}`\n  Name: **{full_name}**\n Email: `{email}`\n\n"

    bot.reply_to(message, text, parse_mode="Markdown")




# Run bot
bot.polling()
