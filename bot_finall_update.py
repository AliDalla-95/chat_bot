import os
import re
from signal import SIGINT, SIGTERM
import logging
from datetime import datetime
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton, 
    KeyboardButton, 
    ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
import psycopg2
import ocr_processor
import scan_image4
import image_processing
import config
import phonenumbers
from phonenumbers import geocoder

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot_errors.log'
)
logger = logging.getLogger(__name__)

# Global dictionaries for state management
pending_submissions = {}  # Format: {user_id: {link_id, chat_id, message_id, description}}
user_pages = {}

# Conversation states
EMAIL, PHONE = range(2)

def connect_db():
    """Create and return a PostgreSQL database connection"""
    try:
        return psycopg2.connect(config.DATABASE_URL)
    except psycopg2.Error as e:
        logger.error(f"Database connection failed: {e}")
        raise

##########################
#    Database Functions  #
##########################
def user_exists(telegram_id: int) -> bool:
    """Check if user exists in database"""
    try:
        with connect_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM users WHERE telegram_id = %s",
                    (telegram_id,)
                )
                return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Error in user_exists: {e}")
        return False

def store_message_id(telegram_id: int, chat_id: int, link_id: int, message_id: int) -> None:
    """Store Telegram message ID with user and chat context"""
    try:
        with connect_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO link_messages 
                        (telegram_id, chat_id, link_id, message_id) 
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (telegram_id, chat_id, link_id) 
                    DO UPDATE SET message_id = EXCLUDED.message_id
                """, (telegram_id, chat_id, link_id, message_id))
                conn.commit()
    except Exception as e:
        logger.error(f"Error storing message ID: {e}")

def get_message_id(telegram_id: int, chat_id: int, link_id: int) -> int:
    """Get message ID for specific user and chat"""
    try:
        with connect_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT message_id FROM link_messages 
                    WHERE telegram_id = %s AND chat_id = %s AND link_id = %s
                """, (telegram_id, chat_id, link_id))
                result = cursor.fetchone()
                return result[0] if result else None
    except Exception as e:
        logger.error(f"Error getting message ID: {e}")
        return None

def get_allowed_links(telegram_id: int) -> list:
    """Retrieve links available for the user"""
    try:
        with connect_db() as conn:
            with conn.cursor() as cursor:
                query = """
                    SELECT l.id, l.youtube_link, l.description, l.adder, l.channel_id
                    FROM links l
                    LEFT JOIN user_link_status uls 
                        ON l.channel_id = uls.channel_id  AND uls.telegram_id = %s
                    WHERE uls.processed IS NULL OR uls.processed = 0
                    ORDER BY l.id DESC
                """
                cursor.execute(query, (telegram_id,))
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error in get_allowed_links: {e}")
        return []

def mark_link_processed(telegram_id: int, link_id: int, res) -> None:
    """Mark a link as processed for the user"""
    try:
        with connect_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO user_link_status (telegram_id, link_id, channel_id, processed)
                    VALUES (%s, %s, %s, 1)
                    ON CONFLICT (telegram_id, link_id, channel_id) 
                    DO UPDATE SET processed = EXCLUDED.processed
                """, (telegram_id, link_id, res))
                conn.commit()
    except Exception as e:
        logger.error(f"Error in mark_link_processed: {e}")
        conn.rollback()

def update_user_points(telegram_id: int, points: int = 1) -> None:
    """Update user's points balance"""
    try:
        with connect_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE users 
                    SET points = points + %s
                    WHERE telegram_id = %s
                """, (points, telegram_id))
                conn.commit()
    except Exception as e:
        logger.error(f"Error in update_user_points: {e}")
        conn.rollback()

def update_likes(link_id: int, points: int = 1) -> None:
    """Update user's points balance"""
    try:
        with connect_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE likes SET channel_likes = channel_likes + %s
            WHERE id = %s
            """, (1,link_id))
            conn.commit()

    except Exception as e:
        logger.error(f"Error in update_likes: {e}")
        conn.rollback()
     

##########################
#    Command Handlers    #
##########################
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display main menu keyboard based on user language"""
    try:
        user_lang = update.effective_user.language_code or 'en'
        
        if user_lang.startswith('ar'):
            # Arabic menu
            keyboard = [
                ["بدء 👋", "تسجيل 📝"],
                ["الملف الشخصي 📋", "عرض المهام 🔍"]
            ]
            menu_text = "اختر أمرا من القائمة"
        else:
            # English menu (default)
            keyboard = [
                ["👋 Start", "📝 Register"],
                ["📋 Profile", "🔍 View Links"]
            ]
            menu_text = "Choose a command:"
            
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(menu_text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in show_menu: {e}")
        await update.message.reply_text("⚠️ Couldn't display menu. Please try again.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    try:
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name
        user_lang = update.effective_user.language_code or 'en'
        if await is_banned(user_id):
            msg = "🚫 تم إلغاء وصولك " if user_lang.startswith('ar') else "🚫 Your access has been revoked"
            await update.message.reply_text(user_name+" "+msg)
            return
        if user_exists(user_id):
            if user_id in config.ADMIN_IDS:
                msg = "أهلا وسهلا بك أدمن! 🛡️" if user_lang.startswith('ar') else "Welcome back Admin! 🛡️"
                await update.message.reply_text(msg)
            else:
                msg = "أهلا بعودتك 🎉" if user_lang.startswith('ar') else "Welcome back ! 🎉"
                await update.message.reply_text(user_name+" "+msg)
            await show_menu(update, context)
        else:
            msg = "أهلا وسهلا بك من فضلك قم بالتسجيل أولا " if user_lang.startswith('ar') else "Welcome ! Please Register First"
            await update.message.reply_text(user_name+" "+msg)
            await show_menu(update, context)
    except Exception as e:
        logger.error(f"Error in start: {e}")
        msg = "! لا يمكن معالجة طلبك حاليا يرجى المحاولة لاحقا ⚠️" if user_lang.startswith('ar') else "⚠️ Couldn't process your request. Please try again."
        await update.message.reply_text(msg)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start registration process"""
    try:
        user_id = update.effective_user.id
        user_lang = update.effective_user.language_code or 'en'
        if await is_banned(user_id):
            msg = "تم إلغاء وصولك 🚫 "  if user_lang.startswith('ar') else "🚫 Your access has been revoked"
            await update.message.reply_text(msg)
            return ConversationHandler.END
        if user_exists(user_id):
            msg = "لا حاجة لإعادة التسجيل أنت مسجل بالفعل ✅ " if user_lang.startswith('ar') else "You're already registered! ✅"
            await update.message.reply_text(msg)
            return ConversationHandler.END

        msg = "من فضلك قم بإدخال بريدك الإلكتروني للمتابعة" if user_lang.startswith('ar') else "Please enter your email address:"
        await update.message.reply_text(msg)
        return EMAIL
    except Exception as e:
        logger.error(f"Error in register: {e}")
        msg = "يمكنك التسجيل الآن حاول لاحقا ⚠️ " if user_lang.startswith('ar') else "⚠️ Couldn't start registration. Please try again."
        await update.message.reply_text(msg)
        return ConversationHandler.END

async def process_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process email input and request phone number"""
    try:
        user_lang = update.effective_user.language_code or 'en'
        email = update.message.text.strip()
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
            msg = "صيغة الإيميل ليست صحيحة يرجى إدخال بريدك الإلكتروني بشكل صحيح ⚠️" if user_lang.startswith('ar') else "Invalid email format ⚠️"
            raise ValueError(msg)
            
        context.user_data['email'] = email
        
        msg = "يرجى الضغط على زر تأكيد رقم هاتفك من القائمة لتأكيد الرقم 📱" if user_lang.startswith('ar') else "📱 Share Phone Number"
        contact_keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton(msg, request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        msg = " من فضلك قم بتأكيد رقم هاتفك لمتابعة التسجيل " if user_lang.startswith('ar') else "Please share your phone number:"
        await update.message.reply_text(
            msg,
            reply_markup=contact_keyboard
        )
        return PHONE
    except Exception as e:
        msg = "صيغة البريد الإلكتروني التي قمت بإدخالها ليست صحيحة يرجى كتابة بريدك الإلكتروني لمتابعة التسجيل ❌ " if user_lang.startswith('ar') else "❌ Invalid email format! Please enter a valid email."
        logger.warning(f"Invalid email input: {e}")
        await update.message.reply_text(msg)
        return EMAIL

async def process_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process contact information and complete registration"""
    try:
        user_lang = update.effective_user.language_code or 'en'
        user = update.effective_user
        contact = update.message.contact
        
        if contact.user_id != user.id:
            msg = "من فضلك قم بمشاركة رقم هاتفك الصحيح ❌ " if user_lang.startswith('ar') else "❌ Please share your own phone number!"
            await update.message.reply_text(msg)
            return PHONE

        phone_number = "+" + contact.phone_number
        full_name = user.name
        
        try:
            parsed_number = phonenumbers.parse(phone_number, None)
            country = geocoder.description_for_number(parsed_number, "en") or "Unknown"
        except phonenumbers.NumberParseException:
            country = "Unknown"

        email = context.user_data.get('email')
        registration_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with connect_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO users (telegram_id, full_name, email, phone, country, registration_date) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (user.id, full_name, email, phone_number, country, registration_date)
                )
                conn.commit()
        msg1 = f"✅ تم إكمال التسجيل بنجاح :\n"
        f"👤 أسمك : {escape_markdown(full_name)}\n"
        f"📧 بريدك الإلكتروني : {escape_markdown_2(email)}\n"
        f"📱 رقم هاتفك : {escape_markdown_2(phone_number)}\n"
        f"🌍 بلدك : {escape_markdown(country)}\n"
        f"⭐ تاريخ التسجيل : {escape_markdown(registration_date)}"
         
        msg2 = f"✅ Registration Complete:\n"
        f"👤 Name: {escape_markdown(full_name)}\n"
        f"📧 Email: {escape_markdown_2(email)}\n"
        f"📱 Phone: {escape_markdown_2(phone_number)}\n"
        f"🌍 Country: {escape_markdown(country)}\n"
        f"⭐ Registration Date: {escape_markdown(registration_date)}"
        
          
        if user_lang.startswith('ar'):
            await update.message.reply_text(
                msg1,
                reply_markup=ReplyKeyboardRemove()
                )
            
        else:
            await update.message.reply_text(
                msg2,
                reply_markup=ReplyKeyboardRemove()
                )
        await show_menu(update, context)
        
    except psycopg2.IntegrityError:
        msg = "أنت مسجل بالفعل ⚠️ " if user_lang.startswith('ar') else "⚠️ You're already registered!"
        await update.message.reply_text(msg)
    except Exception as e:
        msg = "فشلت عملية التسجيل يرجى إعادة المحاولة لاحقا ⚠️ " if user_lang.startswith('ar') else "⚠️ Registration failed. Please try again."
        logger.error(f"Registration error: {e}")
        await update.message.reply_text(msg)
    finally:
        context.user_data.clear()
    return ConversationHandler.END

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display user profile"""
    try:
        user_lang = update.effective_user.language_code or 'en'
        user_id = update.effective_user.id
        if await is_banned(user_id):
            msg = "تم إلغاء وصولك 🚫 " if user_lang.startswith('ar') else "🚫 Your access has been revoked"
            await update.message.reply_text(msg)
            return
        profile = get_profile(user_id)
        if profile:
            _, name, email, phone, country, reg_date, points = profile
            if user_lang.startswith('ar'):
                msg = (f"📋 *ملفك الشخصي :*\n"
                f"👤 أسمك : {escape_markdown(name)}\n"
                f"📧 بريدك الإلكتروني : {escape_markdown(email)}\n"
                f"📱 رقم هاتفك : {escape_markdown(phone)}\n"
                f"🌍 بلدك : {escape_markdown(country)}\n"
                f"⭐ تاريخ التسجيل : {escape_markdown(reg_date)}\n"
                f"🏆 نقاطك : {points}")
            else:
                msg = (f"📋 *Profile Information*\n"
                f"👤 Name: {escape_markdown(name)}\n"
                f"📧 Email: {escape_markdown(email)}\n"
                f"📱 Phone: {escape_markdown(phone)}\n"
                f"🌍 Country: {escape_markdown(country)}\n"
                f"⭐ Registration Date: {escape_markdown(reg_date)}\n"
                f"🏆 Points: {points}")                
            response = (msg)
            await update.message.reply_text(response, parse_mode="MarkdownV2")
        else:
            msg = "أنت لست مسجل قم بالتسجيل أولا ❌ " if user_lang.startswith('ar') else "❌ You're not registered! Register First"
            await update.message.reply_text(msg)
    except Exception as e:
        logger.error(f"Profile error: {e}")
        msg = "لا يمكن عرض الملف الشخصي حاليا يرجى إعادة المحاولة لاحقا ⚠️ " if user_lang.startswith('ar') else "⚠️ Couldn't load profile. Please try again."
        await update.message.reply_text(msg)
        
def get_profile(telegram_id: int) -> tuple:
    """Retrieve user profile data"""
    try:
        with connect_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT telegram_id, full_name, email, phone, country, registration_date, points FROM users WHERE telegram_id = %s",
                    (telegram_id,)
                )
                return cursor.fetchone()
    except Exception as e:
        logger.error(f"Error in get_profile: {e}")
        return None
    
async def view_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display available links"""
    try:
        user_lang = update.effective_user.language_code or 'en'
        user_id = update.effective_user.id
        if await is_banned(user_id):
            msg = "تم إلغاء وصولك 🚫 " if user_lang.startswith('ar') else "🚫 Your access has been revoked"
            await update.message.reply_text(msg)
            return
        if not user_exists(user_id):
            msg = "من فضلك قم بالتسجيل أولا للمتابعة ❌ " if user_lang.startswith('ar') else "❌ Please register first!"
            await update.message.reply_text(msg)
            return

        user_pages[user_id] = 0
        await send_links_page(user_lang,update.effective_chat.id, user_id, 0, context)
    except Exception as e:
        logger.error(f"View links error: {e}")
        msg = " لا يمكن تحميل المهمات حاليا يرجى المحاولة لاحقا ⚠️" if user_lang.startswith('ar') else "⚠️ Couldn't load links. Please try again."
        await update.message.reply_text(msg)

##########################
#    Link Management     #
##########################
async def send_links_page(user_lang: str,chat_id: int, user_id: int, page: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send paginated links with user-specific message tracking"""
    try:
        links, total_pages = get_paginated_links(user_id, page)
        
        if not links:
            msg = " لايوجد مهمات لك الآن قم بتحديث المهمات لرؤية المزيد في حال وجودها 🎉" if user_lang.startswith('ar') else "🎉 No more links available!"
            await context.bot.send_message(chat_id, msg)
            return

        for link in links:
            link_id, yt_link, desc, adder,channel_id = link
            if user_lang.startswith('ar'):
                text = (
                    f"📛 {escape_markdown(desc)}\n"
                    # f"*ID: * {channel_id}\n"
                    f"👤 *بواسطة* {escape_markdown(adder)}\n"
                    f"[🔗 رابط الذهاب للمهمة انقر هنا]({yt_link})"
                    )
                keyboard = [[InlineKeyboardButton(" تنفيذ المهمة وبعد الانتهاء تحميل الصورة 📸", callback_data=f"submit_{link_id}")]]
            else:
                text = (
                    f"📛 {escape_markdown(desc)}\n"
                    # f"*ID: * {channel_id}\n"
                    f"👤 *By:* {escape_markdown(adder)}\n"
                    f"[🔗 YouTube Link]({yt_link})"
                )
                keyboard = [[InlineKeyboardButton("📸 Submit Image", callback_data=f"submit_{link_id}")]]

            message = await context.bot.send_message(
                chat_id,
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="MarkdownV2"
            )
            store_message_id(user_id, chat_id, link_id, message.message_id)

        if total_pages > 1:
            buttons = []
            if user_lang.startswith('ar'):
                if page > 0:
                    buttons.append(InlineKeyboardButton(" الصفحة السابقة ⬅️", callback_data=f"prev_{page-1}"))
                if page < total_pages - 1:
                    buttons.append(InlineKeyboardButton("➡️ الصفحة التالية ", callback_data=f"next_{page+1}"))
                
                if buttons:
                    await context.bot.send_message(
                        chat_id,
                        "انقر لرؤية المزيد",
                        reply_markup=InlineKeyboardMarkup([buttons])
                    )
            else:
                if page > 0:
                    buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"prev_{page-1}"))
                if page < total_pages - 1:
                    buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"next_{page+1}"))
                
                if buttons:
                    await context.bot.send_message(
                        chat_id,
                        "Navigate between pages:",
                        reply_markup=InlineKeyboardMarkup([buttons])
                    )
                
                
    except Exception as e:
        logger.error(f"Error sending links: {e}")
        msg = " لا يمكن عرض المهمات الآن يرجى تحديث المهمات لرؤيتها ⚠️" if user_lang.startswith('ar') else "⚠️ Couldn't load links. Please try later."
        await context.bot.send_message(chat_id, msg)

async def handle_text_commands(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle menu text commands in both languages"""
    try:
        text = update.message.text
        user_lang = update.effective_user.language_code or 'en'
        
        # Command mapping for both languages
        command_map = {
            # English commands
            "👋 Start": "start",
            "📝 Register": "register",
            "📋 Profile": "profile",
            "🔍 View Links": "view_links",
            # Arabic commands
            "بدء 👋" : "start",
            "تسجيل 📝": "register",
            "الملف الشخصي 📋": "profile",
            "عرض المهام 🔍": "view_links"
        }

        action = command_map.get(text)
        
        if action == "start":
            await start(update, context)
        elif action == "register":
            msg = "جاري بدء التسجيل..." if user_lang.startswith('ar') else "Starting registration..."
            await update.message.reply_text(msg)
            await register(update, context)
        elif action == "profile":
            await profile_command(update, context)
        elif action == "view_links":
            await view_links(update, context)
        else:
            msg = "أمر غير معروف. يرجى استخدام أزرار القائمة ❌ " if user_lang.startswith('ar') else "❌ Unknown command. Please use the menu buttons."
            await update.message.reply_text(msg)
            
    except Exception as e:
        logger.error(f"Text command error: {e}")
        error_msg = "تعذر معالجة الأمر. يرجى المحاولة مرة أخرى ⚠️ " if user_lang.startswith('ar') else "⚠️ Couldn't process command. Please try again."
        await update.message.reply_text(error_msg)

async def navigate_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle pagination navigation for links list"""
    try:
        user_lang = update.effective_user.language_code or 'en'
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        action, page_str = query.data.split('_')
        new_page = int(page_str)
        user_pages[user_id] = new_page
        await send_links_page(user_lang,query.message.chat_id, user_id, new_page, context)
        await query.message.delete()
    except Exception as e:
        logger.error(f"Pagination error: {e}")
        if 'query' in locals():
            error_msg = "تعذر تحميل الصفحة. يرجى المحاولة مرة أخرى ⚠️ " if user_lang.startswith('ar') else "⚠️ Couldn't load page. Please try again."
            await query.message.reply_text(error_msg)

##########################
#    Image Submission    #
##########################
async def handle_submit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle image submission requests with user-specific context"""
    try:
        user_lang = update.effective_user.language_code or 'en'
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        link_id = int(query.data.split("_")[1])
        
        message_id = get_message_id(user_id, chat_id, link_id)
        if not message_id:
            msg = " تم تعطيل الجلسة يرجى تحديث قائمة المهام ⚠️" if user_lang.startswith('ar') else "⚠️ Session expired. Please reload links."
            await query.message.reply_text(msg)
            return
            
        allowed_links = get_allowed_links(user_id)
        if not any(link[0] == link_id for link in allowed_links):
            msg = " هذه المهمة لم تعد متاحة لك ⚠️" if user_lang.startswith('ar') else "⚠️ This link is no longer available."
            await query.message.reply_text(msg)
            return
            
        description = get_link_description(link_id)
        if not description:
            msg = " خطأ في تفاصيل المهمة قم بتحديث المهمات ❌" if user_lang.startswith('ar') else "❌ Link details missing"
            await query.message.reply_text("❌ Link details missing")
            return
            
        pending_submissions[user_id] = {
            'link_id': link_id,
            'chat_id': chat_id,
            'message_id': message_id,
            'description': description
        }
        
        if user_lang.startswith('ar'):
            textt=f"📸 خذ لقطة الشاشة للقناة وأرسلها هنا : {description}"
        else:
            textt=f"📸 Submit image for: {description}"
            
        await context.bot.send_message(
            chat_id=chat_id,
            text=textt,
            reply_to_message_id=message_id
        )

    except Exception as e:
        logger.error(f"Submit error: {e}")
        msg = " خطأ في تفاصيل المهمة قم بتحديث المهمات ❌" if user_lang.startswith('ar') else "❌ Link details missing"
        await query.message.reply_text(msg)


def get_link_description(link_id: int) -> str:
    """Get description for a specific link"""
    try:
        with connect_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT description FROM links WHERE id = %s",
                    (link_id,))
                result = cursor.fetchone()
                return result[0] if result else None
    except Exception as e:
        logger.error(f"Error in get_link_description: {e}")
        return None
    
    
async def process_image_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle image verification with user-specific context"""
    try:
        user_lang = update.effective_user.language_code or 'en'
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        if user_id not in pending_submissions:
            msg = " خطأ يرجى تحديث المهمات من جديد ❌" if user_lang.startswith('ar') else "❌ No active submission!"
            await update.message.reply_text(msg)
            return
            
        submission = pending_submissions[user_id]
        link_id = submission['link_id']
        message_id = submission['message_id']
        description = submission['description']
        
        photo_file = await update.message.photo[-1].get_file()
        image_path = f"temp_{user_id}_{link_id}.jpg"
        await photo_file.download_to_drive(image_path)
        
        msg = " جاري التحقق يرجى الانتظار٫٫٫٫٫٫٫٫ 🔍" if user_lang.startswith('ar') else "🔍 Verifying..."
        processing_msg = await update.message.reply_text(
            msg,
            reply_to_message_id=message_id
        )

        verification_passed = False
        try:
            if scan_image4.check_text_in_image(image_path, description):
                verification_passed = True
        except Exception as e:
            logger.error(f"Image processing error: {e}")
        
        if verification_passed:
            try:
                with connect_db() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "SELECT channel_id FROM links WHERE id = %s",
                            (link_id,)
                        )
                        result = cursor.fetchone()
                        res= result[0]
            except Exception as e:
                logger.error(f"Ban check error: {e}")
                return False
            mark_link_processed(user_id, link_id, res)
            update_user_points(user_id)
            update_likes(link_id)
            msg = " تهانينا لقد كسبت نقطة واحدة +١ لنقاطك وتم حذف هذه المهمة عنك يرجى الانتقال لمهمة أخرى ✅" if user_lang.startswith('ar') else "✅ Verification successful! +1 point"
            await update.message.reply_text(
                msg,
                reply_to_message_id=message_id
            )
        else:
            msg = " فشل التحقق يبدو أنك غير مشترك بالقناة يرجى الاشتراك ثم إعادة المحاولة ❌" if user_lang.startswith('ar') else "❌ Verification failed. Try again."
            await update.message.reply_text(
                msg,
                reply_to_message_id=message_id
            )

        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=processing_msg.message_id
        )

    except Exception as e:
        logger.error(f"Image error: {e}")
        msg = " خطأ في معالجة الطلب يرجى تحديث المهمات وإعادة المحاولة لاحقا ⚠️" if user_lang.startswith('ar') else "⚠️ Processing error. Please try again."
        await update.message.reply_text("⚠️ Processing error. Please try again.")
    finally:
        if 'image_path' in locals() and os.path.exists(image_path):
            os.remove(image_path)
        if user_id in pending_submissions:
            del pending_submissions[user_id]

##########################
#    Helper Functions    #
##########################
def escape_markdown(text: str) -> str:
    """Escape MarkdownV2 special characters"""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(['\\' + c if c in escape_chars else c for c in text])

def escape_markdown_2(text: str) -> str:
    """Escape all MarkdownV2 special characters"""
    escape_chars = r'_*[]()~`>#-=|{}!'
    return ''.join(['\\' + char if char in escape_chars else char for char in text])

def get_paginated_links(user_id: int, page: int = 0, per_page: int = 5) -> tuple:
    """Get paginated list of links"""
    try:
        links = get_allowed_links(user_id)
        total_pages = (len(links) - 1) // per_page + 1
        start = page * per_page
        end = start + per_page
        return links[start:end], total_pages
    except Exception as e:
        logger.error(f"Pagination error: {e}")
        return [], 0

async def is_banned(telegram_id: int) -> bool:
    """Check if user is banned"""
    try:
        with connect_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT is_banned FROM users WHERE telegram_id = %s",
                    (telegram_id,)
                )
                result = cursor.fetchone()
                return bool(result and result[0])
    except Exception as e:
        logger.error(f"Ban check error: {e}")
        return False


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler for all uncaught exceptions"""
    try:
        user_lang = update.effective_user.language_code or 'en'
        logger.error("Unhandled exception:", exc_info=context.error)
        
        if update is not None and update.effective_message:
            msg = " خطأ غير متوقع يرجى إعادة المحاولة لاحقا ⚠️" if user_lang.startswith('ar') else "⚠️ An unexpected error occurred. Please try again later."
            await update.effective_message.reply_text(
                msg
            )
    except Exception as e:
        logger.error(f"Error in error handler: {e}")
        

##########################
#    Main Application    #
##########################
def main() -> None:
    """Configure and start the bot"""
    application = ApplicationBuilder().token(config.TOKEN).build()

    # Conversation handler for registration
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('register', register),
            MessageHandler(filters.Regex(r'^📝 Register$'), register),
            MessageHandler(filters.Regex(r'^/register$'), register),
            MessageHandler(filters.Regex(r'^📝 تسجيل$'), register),
        ],
        states={
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_email)],
            PHONE: [
                MessageHandler(filters.CONTACT, process_phone),
                MessageHandler(filters.ALL, lambda u,c: u.message.reply_text("❌ Please use contact button!"))
            ]
        },
        fallbacks=[CommandHandler('cancel', lambda u,c: ConversationHandler.END)],
    )

    # Register handlers
    handlers = [
        CommandHandler('start', start),
        CommandHandler('menu', show_menu),
        CommandHandler('profile', profile_command),
        CommandHandler('viewlinks', view_links),
        conv_handler,
        CallbackQueryHandler(handle_submit_callback, pattern=r"^submit_\d+$"),
        CallbackQueryHandler(navigate_links, pattern=r"^(prev|next)_\d+$"),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_commands),
        MessageHandler(filters.PHOTO, process_image_upload)
    ]

    for handler in handlers:
        application.add_handler(handler)
    application.add_handler(MessageHandler(filters.ALL, lambda u,c: None))  # Workaround
    application.add_error_handler(lambda u,c: error_handler(u,c))

    # Start bot
    application.run_polling(
        close_loop=False,
        stop_signals=(SIGINT, SIGTERM)
    )

if __name__ == '__main__':
    main()