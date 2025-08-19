import os
import logging
import json
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# --- Configuration ---
# ادمین اصلی ربات - شناسه کاربری خود را اینجا وارد کنید
# برای پیدا کردن شناسه کاربری خود می‌توانید از ربات @userinfobot استفاده کنید
ADMIN_USER_ID = 123456789  # !!! شناسه کاربری ادمین را اینجا قرار دهید

CONFIG_FILE = "telegram_bot/config.json"
OPT_OUT_FILE = "telegram_bot/opt_out_list.json"
JOB_ID = "promotional_message_job"

# Initialize scheduler
scheduler = AsyncIOScheduler(timezone="UTC")

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Helper Functions ---
def load_json_file(filepath):
    """Loads data from a JSON file."""
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    return {} if 'config' in filepath else []

def save_json_file(data, filepath):
    """Saves data to a JSON file."""
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)

def load_config():
    return load_json_file(CONFIG_FILE)

def save_config(config):
    save_json_file(config, CONFIG_FILE)

def get_opt_out_list():
    return load_json_file(OPT_OUT_FILE)

def add_to_opt_out_list(user_id):
    opt_out_list = get_opt_out_list()
    if user_id not in opt_out_list:
        opt_out_list.append(user_id)
        save_json_file(opt_out_list, OPT_OUT_FILE)

def is_admin(update: Update) -> bool:
    """Checks if the user is an admin."""
    return update.effective_user.id == ADMIN_USER_ID

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message."""
    await update.message.reply_text("سلام! من ربات ارسال پیام گروهی هستم. برای مشاهده دستورات از /help استفاده کنید.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays help information."""
    if not is_admin(update):
        await update.message.reply_text("شما اجازه استفاده از این دستور را ندارید.")
        return

    help_text = """
    **دستورات ادمین**
    /help - نمایش این پیام راهنما
    /setgroup `GROUP_ID` - تنظیم گروه هدف برای ارسال پیام. `GROUP_ID` باید شناسه عددی گروه باشد (مثلا: -100123456789).
    /setmessage - تنظیم پیام تبلیغاتی (در مرحله بعد پیاده‌سازی می‌شود).
    /setschedule `CRON` - تنظیم زمان‌بندی ارسال (در مرحله بعد پیاده‌سازی می‌شود).
    /sendnow - ارسال فوری پیام برای تست (در مرحله بعد پیاده‌سازی می‌شود).
    /status - نمایش وضعیت و تنظیمات فعلی ربات.
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

# --- Conversation Handler for /setmessage ---
TYPING_MESSAGE = range(1)

async def set_message_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation to set the message."""
    if not is_admin(update):
        await update.message.reply_text("شما اجازه استفاده از این دستور را ندارید.")
        return ConversationHandler.END

    await update.message.reply_text(
        "لطفا پیام تبلیغاتی خود را ارسال کنید. این پیام می‌تواند شامل متن، عکس و کپشن باشد.\n"
        "برای لغو عملیات، از دستور /cancel استفاده کنید."
    )
    return TYPING_MESSAGE

async def save_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the received message to the config."""
    config = load_config()

    # Reset previous message
    config['message'] = {}

    if update.message.text:
        config['message']['text'] = update.message.text
        config['message']['photo_id'] = None
        config['message']['caption'] = None
        await update.message.reply_text("پیام متنی با موفقیت ذخیره شد.")

    elif update.message.photo:
        # We save the file_id of the largest photo
        photo_id = update.message.photo[-1].file_id
        config['message']['photo_id'] = photo_id
        config['message']['caption'] = update.message.caption or '' # Save caption, even if empty
        config['message']['text'] = None
        await update.message.reply_text("تصویر و کپشن با موفقیت ذخیره شدند.")

    else:
        await update.message.reply_text("نوع پیام پشتیبانی نمی‌شود. لطفا متن یا تصویر ارسال کنید.")
        return TYPING_MESSAGE # Stay in the same state

    save_config(config)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the conversation."""
    await update.message.reply_text("عملیات تنظیم پیام لغو شد.")
    return ConversationHandler.END


async def set_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sets the target group ID."""
    if not is_admin(update):
        await update.message.reply_text("شما اجازه استفاده از این دستور را ندارید.")
        return

    if not context.args:
        await update.message.reply_text("لطفا شناسه گروه را وارد کنید.\nمثال: `/setgroup -100123456789`")
        return

    try:
        group_id = int(context.args[0])
        config = load_config()
        config['target_group_id'] = group_id
        save_config(config)
        await update.message.reply_text(f"گروه هدف با موفقیت روی شناسه {group_id} تنظیم شد.")
    except (IndexError, ValueError):
        await update.message.reply_text("شناسه گروه نامعتبر است. لطفا یک شناسه عددی صحیح وارد کنید.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows the current configuration."""
    if not is_admin(update):
        await update.message.reply_text("شما اجازه استفاده از این دستور را ندارید.")
        return

    config = load_config()
    message_summary = "تنظیم نشده"
    msg_config = config.get('message', {})
    if msg_config.get('text'):
        message_summary = f"متن: {msg_config['text'][:30]}..."
    elif msg_config.get('photo_id'):
        message_summary = f"تصویر (ID: {msg_config['photo_id'][:10]}...)"

    status_text = f"""
    **وضعیت فعلی ربات**
    - **شناسه گروه هدف:** `{config.get('target_group_id', 'تنظیم نشده')}`
    - **زمان‌بندی:** `{config.get('schedule', 'تنظیم نشده')}`
    - **پیام تنظیم شده:** {message_summary}
    """
    await update.message.reply_text(status_text, parse_mode='Markdown')

# --- Scheduler Logic ---
async def reschedule_jobs(application: Application) -> None:
    """Removes the old job and schedules a new one based on the config."""
    config = load_config()
    schedule_str = config.get("schedule")

    # Remove existing job if it exists
    if scheduler.get_job(JOB_ID):
        scheduler.remove_job(JOB_ID)
        logger.info("جاب زمان‌بندی شده قبلی حذف شد.")

    if schedule_str:
        try:
            # Add the new job
            scheduler.add_job(
                send_promotional_message,
                trigger=CronTrigger.from_crontab(schedule_str),
                id=JOB_ID,
                name="Promotional Message",
                args=[application], # Pass application context
            )
            logger.info(f"پیام برای ارسال بر اساس زمان‌بندی '{schedule_str}' تنظیم شد.")
        except Exception as e:
            logger.error(f"خطا در تنظیم جاب زمان‌بندی شده: {e}")
            await application.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=f"خطا در تنظیم زمان‌بندی: `{e}`. لطفا فرمت cron را بررسی کنید.",
                parse_mode='Markdown'
            )


async def set_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sets the cron schedule for messaging and updates the scheduler."""
    if not is_admin(update):
        await update.message.reply_text("شما اجازه استفاده از این دستور را ندارید.")
        return

    if not context.args:
        await update.message.reply_text(
            "لطفا عبارت cron برای زمان‌بندی را وارد کنید.\n"
            "مثال برای هر روز ساعت ۹ صبح: `/setschedule 0 9 * * *`\n"
            "برای پاک کردن زمان‌بندی: `/setschedule none`"
        )
        return

    schedule_str = " ".join(context.args)
    config = load_config()

    if schedule_str.lower() == 'none':
        config['schedule'] = None
        await update.message.reply_text("زمان‌بندی در حال حذف شدن است...")
    else:
        # A simple validation for 5 or 6 parts in cron
        if len(schedule_str.split()) not in [5, 6]:
             await update.message.reply_text("فرمت عبارت cron نامعتبر است. باید شامل ۵ یا ۶ بخش باشد.")
             return
        config['schedule'] = schedule_str
        await update.message.reply_text(f"زمان‌بندی در حال تنظیم روی `{schedule_str}` است...", parse_mode='Markdown')

    save_config(config)
    # Reschedule job immediately
    await reschedule_jobs(context.application)
    await update.message.reply_text("عملیات به‌روزرسانی زمان‌بندی با موفقیت انجام شد.")

# --- Message Sending Logic ---
async def send_promotional_message(application: Application) -> None:
    """Sends the configured message to the target group."""
    config = load_config()
    group_id = config.get('target_group_id')
    message_data = config.get('message', {})

    if not group_id or not message_data:
        logger.warning("ارسال پیام لغو شد: شناسه گروه یا محتوای پیام تنظیم نشده است.")
        return

    text = message_data.get('text')
    photo_id = message_data.get('photo_id')
    caption = message_data.get('caption')

    try:
        if text:
            await application.bot.send_message(chat_id=group_id, text=text)
        elif photo_id:
            await application.bot.send_photo(chat_id=group_id, photo=photo_id, caption=caption)

        logger.info(f"پیام با موفقیت به گروه {group_id} ارسال شد.")

    except Exception as e:
        logger.error(f"خطا در ارسال پیام به گروه {group_id}: {e}")
        # Optionally, send a message to the admin about the failure
        await application.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=f"ربات نتوانست پیام را به گروه {group_id} ارسال کند. لطفا بررسی کنید که ربات در گروه عضو و ادمین باشد.\nخطا: `{e}`",
            parse_mode='Markdown'
        )

async def send_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Triggers the promotional message to be sent immediately."""
    if not is_admin(update):
        await update.message.reply_text("شما اجازه استفاده از این دستور را ندارید.")
        return

    await update.message.reply_text("درخواست ارسال فوری دریافت شد. در حال ارسال پیام...")
    # Using job_queue to run the task in the background
    context.job_queue.run_once(lambda job_context: send_promotional_message(context.application), 1)


# --- Opt-Out and Welcome Logic ---
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome DM to new members with an opt-out option."""
    opt_out_list = get_opt_out_list()
    new_members = update.message.new_chat_members

    for member in new_members:
        if member.id in opt_out_list:
            logger.info(f"کاربر {member.id} در لیست انصراف است، پیام خوشامدگویی ارسال نشد.")
            continue

        # Do not send welcome message to the bot itself
        if member.is_bot:
            continue

        logger.info(f"ارسال پیام خوشامدگویی به کاربر جدید: {member.full_name}")

        keyboard = [
            [InlineKeyboardButton("انصراف از دریافت پیام‌های آتی", callback_data=f"optout_{member.id}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await context.bot.send_message(
                chat_id=member.id,
                text="سلام! به گروه ما خوش آمدید. امیدواریم لحظات خوبی را سپری کنید.",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"ارسال پیام خوشامدگویی به {member.id} با خطا مواجه شد: {e}")


async def opt_out_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the opt-out button press."""
    query = update.callback_query
    await query.answer() # Answer the callback query first

    try:
        user_id_to_opt_out = int(query.data.split('_')[1])

        # Security check: Make sure the person clicking the button is the one being opted out
        if query.from_user.id != user_id_to_opt_out:
            await query.edit_message_text(text="خطا: شما نمی‌توانید برای کاربر دیگری درخواست انصراف دهید.")
            return

        add_to_opt_out_list(user_id_to_opt_out)
        logger.info(f"کاربر {user_id_to_opt_out} به لیست انصراف اضافه شد.")
        await query.edit_message_text(text="شما با موفقیت از لیست دریافت پیام‌های آینده انصراف دادید.")

    except (IndexError, ValueError) as e:
        logger.error(f"خطا در پردازش کلید انصراف: {e}")
        await query.edit_message_text(text="خطایی در پردازش درخواست شما رخ داد.")


async def main() -> None:
    """Start the bot."""
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.error("متغیر TELEGRAM_TOKEN تنظیم نشده است! لطفا آن را در محیط سیستم تعریف کنید.")
        return

    # Using a job_queue for background tasks like send_now
    application = Application.builder().token(token).job_queue().build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("setgroup", set_group))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("setschedule", set_schedule))
    application.add_handler(CommandHandler("sendnow", send_now))

    # Add conversation handler for /setmessage
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("setmessage", set_message_start)],
        states={
            TYPING_MESSAGE: [MessageHandler(filters.TEXT | filters.PHOTO, save_message)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(conv_handler)

    # Add handlers for welcome message and opt-out
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    application.add_handler(CallbackQueryHandler(opt_out_callback, pattern=r'^optout_'))

    # Schedule jobs and start the scheduler
    try:
        scheduler.start()
        logger.info("زمان‌بند (Scheduler) شروع به کار کرد.")
        # Schedule jobs for the first time
        await reschedule_jobs(application)
    except Exception as e:
        logger.error(f"خطا در راه اندازی زمان‌بند: {e}")


    logger.info("ربات در حال اجرا است...")
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
