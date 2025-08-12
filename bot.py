from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Updater, CommandHandler
import os

TOKEN = os.environ.get('TELEGRAM_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://cinema-space-bot.onrender.com')

def start(update, context):
    keyboard = [[
        InlineKeyboardButton(
            "🌌 ОТКРЫТЬ КИНОВСЕЛЕННУЮ", 
            web_app=WebAppInfo(url=WEBHOOK_URL)
        )
    ]]
    update.message.reply_text(
        "Нажмите кнопку ниже, чтобы открыть приложение на полный экран:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

updater = Updater(TOKEN)
updater.dispatcher.add_handler(CommandHandler('start', start))
updater.start_polling()
