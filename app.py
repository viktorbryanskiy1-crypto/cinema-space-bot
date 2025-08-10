from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_from_directory
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, Update
from telegram.ext import Updater, CommandHandler
import os
import threading
import json
from database import *
from werkzeug.utils import secure_filename
import uuid
from datetime import datetime

# Получаем токен и URL из переменных окружения
TOKEN = os.environ.get('TELEGRAM_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://cinema-space-bot.onrender.com')

# Создаем Flask приложение
app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-it'  # Измени на случайный ключ в production

# Конфигурация для загрузки файлов
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # Максимальный размер файла 50MB
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Поддерживаемые форматы файлов
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

# Инициализируем бота
updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher

def start(update, context):
    keyboard = [[
        InlineKeyboardButton(
            "🌌 КиноВселенная", 
            web_app=WebAppInfo(url=WEBHOOK_URL)
        )
    ]]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(
        "🚀 Добро пожаловать в КиноВселенная!\n"
        "✨ Исследуй космос кино\n"
        "🎬 Лучшие моменты из фильмов\n"
       
