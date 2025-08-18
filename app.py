# app.py
import os
import threading
import logging
import uuid
import requests  # Добавлено для получения ссылки от Telegram
import time  # Добавлено для кэширования
import re  # Добавлено для парсинга ссылок
import asyncio  # Добавлено для асинхронных вызовов Telegram API
from datetime import datetime
from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, session, send_from_directory, abort
)
from werkzeug.utils import secure_filename
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, Bot, MenuButtonWebApp, WebAppInfo
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import redis
import json

# -----------------------------
# Импорт функций из database.py
# -----------------------------
from database import (
    get_or_create_user, get_user_role,
    add_moment, add_trailer, add_news,
    get_all_moments, get_all_trailers, get_all_news,
    get_reactions_count, get_comments,
    add_reaction, add_comment,
    authenticate_admin, get_stats,
    delete_item, get_access_settings, update_access_settings,
    init_db, get_item_by_id
)

# --- Logging ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Config ---
TOKEN = os.environ.get('TELEGRAM_TOKEN')
# Исправлено: убраны лишние пробелы
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://cinema-space-bot.onrender.com').strip()
REDIS_URL = os.environ.get('REDIS_URL', None)
if not TOKEN:
    logger.error("TELEGRAM_TOKEN not set!")

# --- Redis ---
redis_client = None
if REDIS_URL:
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        redis_client.ping()
        logger.info("✅ Redis connected via REDIS_URL")
    except Exception as e:
        logger.warning(f"Redis error: {e}")
else:
    try:
        redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        redis_client.ping()
        logger.info("✅ Local Redis connected")
    except Exception as e:
        logger.warning(f"Local Redis not available: {e}")
        redis_client = None

# --- Flask ---
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'super-secret-key')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename, allowed_exts):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_exts

# --- Telegram Bot ---
updater = None
dp = None
pending_video_data = {}

# --- НОВОЕ: Кэш для прямых ссылок ---
video_url_cache = {}

def get_direct_video_url(file_id):
    """Преобразует file_id в прямую ссылку для веба"""
    bot_token = TOKEN
    if not bot_token:
        logger.error("TELEGRAM_TOKEN не установлен для генерации ссылки")
        return None

    try:
        # ИСПРАВЛЕНО: Убраны лишние пробелы в URL
        file_info_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
        logger.debug(f"Запрос к Telegram API: {file_info_url}")
        response = requests.get(file_info_url, timeout=10)
        response.raise_for_status()

        json_response = response.json()
        logger.debug(f"Ответ от Telegram API: {json_response}")
        if not json_response.get('ok'):
            logger.error(f"Ошибка от Telegram API: {json_response}")
            return None

        file_path = json_response['result']['file_path']
        # ИСПРАВЛЕНО: Убраны лишние пробелы в URL
        direct_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"

        logger.info(f"Сгенерирована прямая ссылка для file_id {file_id}")
        return direct_url
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка сети при получении ссылки для file_id {file_id}: {e}")
        return None
    except KeyError as e:
        logger.error(f"Ошибка парсинга ответа Telegram для file_id {file_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Неизвестная ошибка при получении ссылки для file_id {file_id}: {e}")
        return None


def get_cached_direct_video_url(file_id, cache_time=3600):
    """Кэшированное получение прямой ссылки"""
    current_time = time.time()

    # Проверяем кэш
    if file_id in video_url_cache:
        url, expire_time = video_url_cache[file_id]
        if current_time < expire_time:
            logger.debug(f"Ссылка для file_id {file_id} получена из кэша")
            return url

    # Получаем новую ссылку
    logger.debug(f"Генерация новой ссылки для file_id {file_id}")
    url = get_direct_video_url(file_id)
    if url:
        # Кэшируем
        video_url_cache[file_id] = (url, current_time + cache_time)
        logger.debug(f"Ссылка для file_id {file_id} закэширована")
        return url

    return None

# --- ИСПРАВЛЕННОЕ: Функция для извлечения видео из поста Telegram ---
# (Обновлённая версия с исправлением для PTB v13.15 - убран await)
async def extract_video_url_from_telegram_post(post_url):
    """
    Извлекает прямую ссылку на видео из поста Telegram.
    Совместимо с python-telegram-bot v13.15.
    """
    try:
        logger.info(f"Попытка извлечь видео из поста: {post_url}")
        
        # ИСПРАВЛЕНО: Убраны лишние пробелы в регулярных выражениях
        # Парсим ссылку
        # Пример: https://t.me/your_channel/123
        # Для публичных каналов: https://t.me/channelname/messageid
        # Для приватных каналов (с /c/): https://t.me/c/chatid/messageid
        # Убираем возможные пробелы в конце URL
        post_url = post_url.strip()
        public_match = re.search(r'https?://t\.me/([^/\s]+)/(\d+)', post_url)
        private_match = re.search(r'https?://t\.me/c/(\d+)/(\d+)', post_url)

        chat_id_or_username = None
        message_id = None

        if public_match:
            # Для публичных каналов имя пользователя начинается с @
            chat_id_or_username = "@" + public_match.group(1)
            message_id = int(public_match.group(2))
            logger.debug(f"Найден публичный канал: {chat_id_or_username}, сообщение: {message_id}")
        elif private_match:
            # Для приватных каналов/супергрупп используем отрицательный chat_id
            # ID из t.me/c/ нужно преобразовать
            # Пример: t.me/c/192847563/10 -> chat_id = -100192847563
            raw_id = int(private_match.group(1))
            # Правильное преобразование ID приватного чата/канала
            chat_id_or_username = -1000000000000 - raw_id
            message_id = int(private_match.group(2))
            logger.debug(f"Найден приватный канал (ID): {chat_id_or_username}, сообщение: {message_id}")
        else:
            logger.error(f"Неверный формат ссылки на пост: {post_url}")
            return None, "Неверный формат ссылки на пост Telegram. Используйте формат https://t.me/channel/123 или https://t.me/c/123456789/123"

        if chat_id_or_username is None or message_id is None:
             return None, "Не удалось распарсить ссылку на пост"

        # Создаем бота
        bot = Bot(token=TOKEN)

        # --- ИСПРАВЛЕНИЕ: Убран await, так как forward_message в v13.15 не асинхронный ---
        try:
            # ВАЖНО: НЕТ await здесь
            forwarded_message = bot.forward_message(
                chat_id=chat_id_or_username,      # Куда пересылать - в тот же чат
                from_chat_id=chat_id_or_username, # Откуда - из того же чата
                message_id=message_id            # Какое сообщение
            )
            message = forwarded_message
            logger.debug("Сообщение успешно получено через forward_message (в тот же чат)")
        except Exception as e1:
            logger.warning(f"Не удалось получить сообщение через forward в тот же чат: {e1}")
            # Вариант 2 (если бот не админ): Переслать сообщение себе или в тестовый чат
            # ВАЖНО: Замените YOUR_ADMIN_CHAT_ID на реальный ID чата админа или тестового чата
            # где бот точно является участником
            YOUR_ADMIN_CHAT_ID = -1003045387627 # <<<--- ВАШ ID ТЕСТОВОЙ ГРУППЫ
            try:
                # ВАЖНО: НЕТ await здесь тоже
                forwarded_message = bot.forward_message(
                    chat_id=YOUR_ADMIN_CHAT_ID,       # Куда пересылать - админу/в тестовый чат
                    from_chat_id=chat_id_or_username, # Откуда - из исходного чата
                    message_id=message_id            # Какое сообщение
                )
                message = forwarded_message
                logger.debug("Сообщение успешно получено через forward_message (в админский чат)")
            except Exception as e2:
                logger.error(f"Не удалось получить сообщение через forward: {e1}, {e2}")
                return None, "Не удалось получить сообщение. Убедитесь, что бот администратор канала или имеет доступ к сообщению."

        # --- Конец исправления ---

        if not message:
            logger.error("Сообщение не найдено или бот не имеет доступа")
            return None, "Сообщение не найдено. Убедитесь, что бот является администратором канала или имеет доступ к сообщению."

        if not message.video:
            logger.error("В посте нет видео")
            return None, "В указанном посте не найдено видео."

        # Получаем file_id
        file_id = message.video.file_id
        logger.info(f"Найден file_id: {file_id}")

        # Генерируем прямую ссылку
        direct_url = get_cached_direct_video_url(file_id)

        if not direct_url:
            logger.error("Не удалось получить прямую ссылку из file_id")
            return None, "Не удалось получить прямую ссылку на видео из Telegram."

        logger.info(f"Успешно извлечена прямая ссылка: {direct_url}")
        return direct_url, None

    except Exception as e:
        logger.error(f"Ошибка извлечения видео из поста {post_url}: {e}", exc_info=True)
        return None, f"Ошибка при обработке ссылки на пост: {str(e)}"


# Синхронная обертка для Flask
def extract_video_url_sync(post_url):
    """Синхронная обертка для асинхронной функции извлечения видео"""
    try:
        logger.debug("Получение или создание event loop для асинхронного вызова")
        # Для Flask (синхронного) нужно запускать асинхронный код
        try:
            # Попробуем получить текущий event loop
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # Если его нет (например, в новом потоке), создаем новый
            logger.debug("Создание нового event loop")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        logger.debug("Запуск асинхронной функции extract_video_url_from_telegram_post")
        result = loop.run_until_complete(extract_video_url_from_telegram_post(post_url))
        logger.debug(f"Асинхронная функция завершена, результат: {result}")
        return result
    except Exception as e:
        logger.error(f"Ошибка в синхронной обертке extract_video_url_sync: {e}", exc_info=True)
        return None, f"Ошибка обработки запроса: {e}"

# --- НОВОЕ: Функция для установки Menu Button ---
def set_menu_button():
    """Устанавливает кнопку меню для бота"""
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN не установлен для установки Menu Button")
        return

    try:
        bot = Bot(token=TOKEN)
        # URL вашего веб-приложения
        # ВАЖНО: Убедитесь, что WEBHOOK_URL корректен
        app_url = WEBHOOK_URL.strip('/') + '/?mode=fullscreen'
        
        menu_button = MenuButtonWebApp(
            text="🌌 КиноВселенная", # Текст на кнопке
            web_app=WebAppInfo(url=app_url) # URL веб-приложения
        )
        
        # Устанавливаем кнопку меню для бота
        # Это сделает кнопку доступной для всех пользователей
        bot.set_chat_menu_button(menu_button=menu_button)
        logger.info(f"✅ Menu Button установлена: {app_url}")
    except Exception as e:
        logger.error(f"❌ Ошибка установки Menu Button: {e}", exc_info=True)

# --- Telegram Bot Handlers ---
if TOKEN:
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # --- ИСПРАВЛЕНО: Обработчик команды /start ---
    def start(update, context):
        """Обработчик команды /start"""
        user = update.message.from_user
        telegram_id = str(user.id)
        get_or_create_user(
            telegram_id=telegram_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        keyboard = [[
            InlineKeyboardButton(
                "🌌 КиноВселенная",
                web_app=WebAppInfo(url=f"{WEBHOOK_URL}?mode=fullscreen")
            )
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(
            "🚀 Добро пожаловать в КиноВселенную!\n"
            "✨ Исследуй космос кино\n"
            "🎬 Лучшие моменты из фильмов\n"
            "🎥 Свежие трейлеры\n"
            "📰 Горячие новости\n"
            "Нажми кнопку для входа в приложение",
            reply_markup=reply_markup
        )

# --- Helpers ---
def save_uploaded_file(file_storage, allowed_exts):
    if file_storage and allowed_file(file_storage.filename, allowed_exts):
        filename = secure_filename(file_storage.filename)
        unique_name = f"{uuid.uuid4()}_{filename}"
        path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
        file_storage.save(path)
        return f"/uploads/{unique_name}"
    return None

def cache_get(key):
    if not redis_client: return None
    try:
        raw = redis_client.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None

def cache_set(key, value, expire=300):
    if redis_client:
        try:
            redis_client.set(key, json.dumps(value), ex=expire)
        except Exception:
            pass

def cache_delete(key):
    if redis_client:
        try:
            redis_client.delete(key)
        except Exception:
            pass

def build_extra_map(data, item_type_plural):
    """Добавляет реакции и комментарии к каждому элементу данных."""
    extra = {}
    # ИСПРАВЛЕНО: Полная строка цикла
    for row in data:
        if len(row) == 0:
            continue
        item_id = row[0]
        reactions = get_reactions_count(item_type_plural, item_id) or {'like':0,'dislike':0,'star':0,'fire':0}
        comments_count = len(get_comments(item_type_plural, item_id) or [])
        extra[item_id] = {'reactions': reactions, 'comments_count': comments_count}
    return extra

# --- Routes (пользовательские) ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/moments')
def moments():
    try:
        logger.info("Запрос к /moments")
        # Отключаем кэш для теста
        # cached = cache_get('moments_list')
        # if cached:
        #     logger.info("moments_list загружен из кэша")
        #     return render_template('moments.html', moments=cached, extra_by_id={})
        
        logger.info("Получение всех моментов из БД...")
        data = get_all_moments() or []
        logger.info(f"Получено {len(data)} моментов из БД")
        
        logger.info("Построение extra_map...")
        extra_map = build_extra_map(data, 'moments')
        logger.info("extra_map построен успешно")

        # --- ИСПРАВЛЕНИЕ: Объединяем данные ---
        combined_data = []
        for row in 
            item_id = row[0]
            # Создаем словарь для удобства работы в шаблоне
            # Предполагаем, что row это tuple: (id, title, description, video_url, created_at)
            item_dict = {
                'id': row[0],
                'title': row[1] if len(row) > 1 else '',
                'description': row[2] if len(row) > 2 else '',
                'video_url': row[3] if len(row) > 3 else '',
                'created_at': row[4] if len(row) > 4 else None
            }
            # Добавляем extra данные
            extra_info = extra_map.get(item_id, {'reactions': {'like':0,'dislike':0,'star':0,'fire':0}, 'comments_count': 0})
            # Убедимся, что reactions - это словарь
            if isinstance(extra_info.get('reactions'), dict):
                item_dict['reactions'] = extra_info['reactions']
            else:
                item_dict['reactions'] = {'like':0,'dislike':0,'star':0,'fire':0}
            
            item_dict['comments_count'] = extra_info.get('comments_count', 0)
            combined_data.append(item_dict)
        
        logger.info("Данные объединены успешно")
        # Передаем объединенный список
        return render_template('moments.html', moments=combined_data)
        # --- ИСПРАВЛЕНИЕ КОНЕЦ ---
    except Exception as e:
        logger.error(f"Ошибка в маршруте /moments: {e}", exc_info=True)
        return render_template('moments.html', moments=[]), 500

@app.route('/trailers')
def trailers():
    try:
        logger.info("Запрос к /trailers")
        logger.info("Получение всех трейлеров из БД...")
        data = get_all_trailers() or []
        logger.info(f"Получено {len(data)} трейлеров из БД")
        
        logger.info("Построение extra_map...")
        extra_map = build_extra_map(data, 'trailers')
        logger.info("extra_map построен успешно")

        # --- ИСПРАВЛЕНИЕ: Объединяем данные ---
        combined_data = []
        for row in 
            item_id = row[0]
            # Создаем словарь для удобства работы в шаблоне
            # Предполагаем, что row это tuple: (id, title, description, video_url, created_at)
            item_dict = {
                'id': row[0],
                'title': row[1] if len(row) > 1 else '',
                'description': row[2] if len(row) > 2 else '',
                'video_url': row[3] if len(row) > 3 else '',
                'created_at': row[4] if len(row) > 4 else None
            }
            # Добавляем extra данные
            extra_info = extra_map.get(item_id, {'reactions': {'like':0,'dislike':0,'star':0,'fire':0}, 'comments_count': 0})
            # Убедимся, что reactions - это словарь
            if isinstance(extra_info.get('reactions'), dict):
                item_dict['reactions'] = extra_info['reactions']
            else:
                item_dict['reactions'] = {'like':0,'dislike':0,'star':0,'fire':0}
            
            item_dict['comments_count'] = extra_info.get('comments_count', 0)
            combined_data.append(item_dict)
        
        logger.info("Данные объединены успешно")
        return render_template('trailers.html', trailers=combined_data)
        # --- ИСПРАВЛЕНИЕ КОНЕЦ ---
    except Exception as e:
        logger.error(f"Ошибка в маршруте /trailers: {e}", exc_info=True)
        return render_template('trailers.html', trailers=[]), 500

@app.route('/news')
def news():
    try:
        logger.info("Запрос к /news")
        logger.info("Получение всех новостей из БД...")
        data = get_all_news() or []
        logger.info(f"Получено {len(data)} новостей из БД")
        
        logger.info("Построение extra_map...")
        extra_map = build_extra_map(data, 'news')
        logger.info("extra_map построен успешно")

        # --- ИСПРАВЛЕНИЕ: Объединяем данные ---
        combined_data = []
        for row in 
            item_id = row[0]
            # Создаем словарь для удобства работы в шаблоне
            # Предполагаем, что row это tuple: (id, title, text, image_url, created_at)
            item_dict = {
                'id': row[0],
                'title': row[1] if len(row) > 1 else '',
                'text': row[2] if len(row) > 2 else '', # Для новостей используем 'text'
                'image_url': row[3] if len(row) > 3 else '',
                'created_at': row[4] if len(row) > 4 else None
            }
            # Добавляем extra данные
            extra_info = extra_map.get(item_id, {'reactions': {'like':0,'dislike':0,'star':0,'fire':0}, 'comments_count': 0})
            # Убедимся, что reactions - это словарь
            if isinstance(extra_info.get('reactions'), dict):
                item_dict['reactions'] = extra_info['reactions']
            else:
                item_dict['reactions'] = {'like':0,'dislike':0,'star':0,'fire':0}
            
            item_dict['comments_count'] = extra_info.get('comments_count', 0)
            combined_data.append(item_dict)
        
        logger.info("Данные объединены успешно")
        return render_template('news.html', news=combined_data)
        # --- ИСПРАВЛЕНИЕ КОНЕЦ ---
    except Exception as e:
        logger.error(f"Ошибка в маршруте /news: {e}", exc_info=True)
        return render_template('news.html', news=[]), 500

# --- НОВОЕ: Детальные страницы ---
@app.route('/moments/<int:item_id>')
def moment_detail(item_id):
    """Отображает страницу одного момента."""
    logger.info(f"Запрос к /moments/{item_id}")
    item = get_item_by_id('moments', item_id)
    if not item:
        logger.warning(f"Момент с id={item_id} не найден")
        abort(404)
    reactions = get_reactions_count('moments', item_id)
    comments = get_comments('moments', item_id)
    logger.info(f"Момент {item_id} найден: {item[1] if len(item) > 1 else 'Без названия'}")
    # Преобразуем кортеж item в словарь для шаблона
    item_dict = {
        'id': item[0],
        'title': item[1] if len(item) > 1 else '',
        'description': item[2] if len(item) > 2 else '',
        'video_url': item[3] if len(item) > 3 else '',
        'created_at': item[4] if len(item) > 4 else None
    }
    return render_template('moment_detail.html', item=item_dict, reactions=reactions, comments=comments)

@app.route('/trailers/<int:item_id>')
def trailer_detail(item_id):
    """Отображает страницу одного трейлера."""
    logger.info(f"Запрос к /trailers/{item_id}")
    item = get_item_by_id('trailers', item_id)
    if not item:
        logger.warning(f"Трейлер с id={item_id} не найден")
        abort(404)
    reactions = get_reactions_count('trailers', item_id)
    comments = get_comments('trailers', item_id)
    logger.info(f"Трейлер {item_id} найден: {item[1] if len(item) > 1 else 'Без названия'}")
    # Преобразуем кортеж item в словарь для шаблона
    item_dict = {
        'id': item[0],
        'title': item[1] if len(item) > 1 else '',
        'description': item[2] if len(item) > 2 else '',
        'video_url': item[3] if len(item) > 3 else '',
        'created_at': item[4] if len(item) > 4 else None
    }
    return render_template('trailer_detail.html', item=item_dict, reactions=reactions, comments=comments)

@app.route('/news/<int:item_id>')
def news_detail(item_id):
    """Отображает страницу одной новости."""
    logger.info(f"Запрос к /news/{item_id}")
    item = get_item_by_id('news', item_id)
    if not item:
        logger.warning(f"Новость с id={item_id} не найдена")
        abort(404)
    reactions = get_reactions_count('news', item_id)
    comments = get_comments('news', item_id)
    logger.info(f"Новость {item_id} найдена: {item[1] if len(item) > 1 else 'Без заголовка'}")
    # Преобразуем кортеж item в словарь для шаблона
    item_dict = {
        'id': item[0],
        'title': item[1] if len(item) > 1 else '',
        'text': item[2] if len(item) > 2 else '', # Для новостей используем 'text'
        'image_url': item[3] if len(item) > 3 else '',
        'created_at': item[4] if len(item) > 4 else None
    }
    return render_template('news_detail.html', item=item_dict, reactions=reactions, comments=comments)

# --- API: добавление контента ---
def _get_payload():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form or {}

# --- ОБНОВЛЕННЫЕ API ENDPOINTS ---
@app.route('/api/add_moment', methods=['POST'])
def api_add_moment():
    try:
        payload = _get_payload()
        title = payload.get('title', '').strip()
        desc = payload.get('description', '').strip()

        # --- ИЗМЕНЕНИЯ НАЧАЛО ---
        # Сначала проверяем URL из формы/JSON
        video_url = payload.get('video_url', '').strip()

        # --- НОВАЯ ЛОГИКА: Если это ссылка на пост Telegram ---
        if video_url and ('t.me/' in video_url):
            logger.info(f"Обнаружена ссылка на Telegram пост: {video_url}")
            # Пытаемся извлечь прямую ссылку
            direct_url, error = extract_video_url_sync(video_url)
            if direct_url:
                video_url = direct_url
                logger.info(f"Извлечена прямая ссылка из поста: {video_url[:50]}...")
            else:
                logger.error(f"Ошибка извлечения видео из поста: {error}")
                return jsonify(success=False, error=error), 400 # Возвращаем ошибку клиенту

        # Только если URL (включая извлеченный) не указан, пытаемся сохранить файл
        if not video_url and 'video_file' in request.files:
            saved = save_uploaded_file(request.files['video_file'], ALLOWED_VIDEO_EXTENSIONS)
            if saved:
                video_url = saved

        # Если URL так и не получен, ошибка
        if not video_url:
            logger.error("Не указан video_url, не извлечен из поста и не загружен файл")
            return jsonify(success=False, error="Укажите ссылку на видео, пост Telegram или загрузите файл"), 400

        add_moment(title, desc, video_url)
        cache_delete('moments_list')
        logger.info(f"Добавлен момент: {title}")
        return jsonify(success=True)
        # --- ИЗМЕНЕНИЯ КОНЕЦ ---
    except Exception as e:
        logger.error(f"API add_moment error: {e}", exc_info=True)
        return jsonify(success=False, error=str(e)), 500

@app.route('/api/add_trailer', methods=['POST'])
def api_add_trailer():
    try:
        payload = _get_payload()
        title = payload.get('title', '').strip()
        desc = payload.get('description', '').strip()

        # --- ИЗМЕНЕНИЯ НАЧАЛО ---
        video_url = payload.get('video_url', '').strip()

        # --- НОВАЯ ЛОГИКА: Если это ссылка на пост Telegram ---
        if video_url and ('t.me/' in video_url):
            logger.info(f"Обнаружена ссылка на Telegram пост: {video_url}")
            direct_url, error = extract_video_url_sync(video_url)
            if direct_url:
                video_url = direct_url
                logger.info(f"Извлечена прямая ссылка из поста: {video_url[:50]}...")
            else:
                logger.error(f"Ошибка извлечения видео из поста: {error}")
                return jsonify(success=False, error=error), 400

        if not video_url and 'video_file' in request.files:
            saved = save_uploaded_file(request.files['video_file'], ALLOWED_VIDEO_EXTENSIONS)
            if saved: video_url = saved
        # --- ИЗМЕНЕНИЯ КОНЕЦ ---

        if not video_url:
             logger.error("Не указан video_url, не извлечен из поста и не загружен файл")
             return jsonify(success=False, error="Укажите ссылку на видео, пост Telegram или загрузите файл"), 400

        add_trailer(title, desc, video_url)
        cache_delete('trailers_list')
        logger.info(f"Добавлен трейлер: {title}")
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"API add_trailer error: {e}", exc_info=True)
        return jsonify(success=False, error=str(e)), 500

@app.route('/api/add_news', methods=['POST'])
def api_add_news():
    try:
        payload = _get_payload()
        title = payload.get('title', '').strip()
        # В новостях может быть как text, так и description
        text = payload.get('text', payload.get('description', '')).strip()

        # --- ИЗМЕНЕНИЯ НАЧАЛО ---
        # Для новостей видео может быть не обязательно, но если нужно:
        # video_url = payload.get('video_url', '').strip()
        # if video_url and ('t.me/' in video_url):
        #     # Аналогично для новостей, если добавите блок видео
        #     pass

        image_url = payload.get('image_url', '').strip()
        if not image_url and 'image_file' in request.files:
            saved = save_uploaded_file(request.files['image_file'], ALLOWED_IMAGE_EXTENSIONS)
            if saved: image_url = saved
        # --- ИЗМЕНЕНИЯ КОНЕЦ ---

        add_news(title, text, image_url)
        cache_delete('news_list')
        logger.info(f"Добавлена новость: {title}")
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"API add_news error: {e}", exc_info=True)
        return jsonify(success=False, error=str(e)), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- Reactions & Comments ---
@app.route('/api/reaction', methods=['POST'])
def api_add_reaction():
    try:
        data = request.get_json(force=True)
        item_type = data.get('item_type')
        item_id = int(data.get('item_id'))
        user_id = data.get('user_id', 'anonymous')
        reaction = data.get('reaction')
        success = add_reaction(item_type, item_id, user_id, reaction)
        return jsonify(success=success)
    except Exception as e:
        logger.error(f"API add_reaction error: {e}", exc_info=True)
        return jsonify(success=False, error=str(e)), 500

@app.route('/api/comments', methods=['GET'])
def api_get_comments():
    try:
        item_type = request.args.get('type')
        item_id = int(request.args.get('id'))
        comments = get_comments(item_type, item_id)
        return jsonify(comments=comments)
    except Exception as e:
        logger.error(f"API get_comments error: {e}", exc_info=True)
        return jsonify(comments=[], error=str(e)), 500

@app.route('/api/comment', methods=['POST'])
def api_add_comment():
    try:
        data = request.get_json(force=True)
        item_type = data.get('item_type')
        item_id = int(data.get('item_id'))
        user_name = data.get('user_name', 'Гость')
        text = data.get('text')
        add_comment(item_type, item_id, user_name, text)
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"API add_comment error: {e}", exc_info=True)
        return jsonify(success=False, error=str(e)), 500

# --- Admin ---
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username','')
        password = request.form.get('password','')
        if authenticate_admin(username, password):
            session['admin'] = username
            return redirect(url_for('admin_dashboard'))
        return render_template('admin/login.html', error='Неверный логин или пароль')
    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))

def admin_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if 'admin' not in session:
            return redirect(url_for('admin_login'))
        return func(*args, **kwargs)
    return wrapper

@app.route('/admin')
@admin_required
def admin_dashboard():
    stats = get_stats()
    return render_template('admin/dashboard.html',
        moments_count=stats.get('moments', 0),
        trailers_count=stats.get('trailers', 0),
        news_count=stats.get('news', 0),
        comments_count=stats.get('comments', 0))

# --- НОВЫЙ МАРШРУТ: Отображение формы добавления видео ---
@app.route('/admin/add_video')
@admin_required
def admin_add_video_form():
    """Отображает форму добавления видео."""
    return render_template('admin/add_video.html')

@app.route('/admin/content')
@admin_required
def admin_content():
    moments = get_all_moments() or []
    trailers = get_all_trailers() or []
    news = get_all_news() or []
    return render_template('admin/content.html', moments=moments, trailers=trailers, news=news)

# Исправленные функции удаления (если они отсутствуют в database.py)
def delete_moment(item_id):
    delete_item('moments', item_id)

def delete_trailer(item_id):
    delete_item('trailers', item_id)

def delete_news(item_id):
    delete_item('news', item_id)

@app.route('/admin/delete/<content_type>/<int:content_id>')
@admin_required
def admin_delete(content_type, content_id):
    if content_type == 'moment':
        delete_moment(content_id); cache_delete('moments_list')
    elif content_type == 'trailer':
        delete_trailer(content_id); cache_delete('trailers_list')
    elif content_type == 'news':
        delete_news(content_id); cache_delete('news_list')
    return redirect(url_for('admin_content'))

@app.route('/admin/access')
@admin_required
def admin_access_settings():
    moment_roles = get_access_settings('moment')
    trailer_roles = get_access_settings('trailer')
    news_roles = get_access_settings('news')
    return render_template('admin/access/settings.html',
        moment_roles=moment_roles, trailer_roles=trailer_roles, news_roles=news_roles)

@app.route('/admin/access/update/<content_type>', methods=['POST'])
@admin_required
def admin_update_access(content_type):
    roles = request.form.getlist('roles')
    update_access_settings(content_type, roles)
    return redirect(url_for('admin_access_settings'))

# --- НОВЫЙ МАРШРУТ: API для формы add_video.html ---
@app.route('/admin/add_video_json', methods=['POST'])
@admin_required
def admin_add_video_json():
    """API endpoint для добавления видео через форму add_video.html"""
    try:
        # Этот маршрут ожидает JSON
        data = request.get_json()
        if not data:
            return jsonify(success=False, error="Неверный формат данных (ожидается JSON)"), 400

        title = data.get('title', '').strip()
        description = data.get('description', '').strip()
        category = data.get('category', '').strip() # moment, trailer, news
        post_link = data.get('post_link', '').strip() # Это может быть ссылка на пост или прямой URL

        if not title or not post_link or not category:
            return jsonify(success=False, error="Заполните все обязательные поля"), 400

        if category not in ['moment', 'trailer', 'news']:
             return jsonify(success=False, error="Неверный тип контента"), 400

        video_url = post_link
        # --- НОВАЯ ЛОГИКА: Если это ссылка на пост Telegram ---
        if 't.me/' in post_link:
            logger.info(f"[JSON API] Обнаружена ссылка на Telegram пост: {post_link}")
            # Пытаемся извлечь прямую ссылку
            direct_url, error = extract_video_url_sync(post_link)
            if direct_url:
                video_url = direct_url
                logger.info(f"[JSON API] Извлечена прямая ссылка из поста: {video_url[:50]}...")
            else:
                logger.error(f"[JSON API] Ошибка извлечения видео из поста: {error}")
                return jsonify(success=False, error=error), 400

        # --- Вызов соответствующей функции добавления ---
        if category == 'moment':
            add_moment(title, description, video_url)
            cache_delete('moments_list')
        elif category == 'trailer':
            add_trailer(title, description, video_url)
            cache_delete('trailers_list')
        elif category == 'news':
            # Для новостей, если вы хотите добавлять видео, нужно изменить add_news
            # Пока что добавляем как изображение, если это ссылка на изображение
            # Или оставляем image_url пустым
            add_news(title, description, video_url if video_url.startswith(('http://', 'https://')) else None)
            cache_delete('news_list')

        logger.info(f"[JSON API] Добавлен {category}: {title}")
        return jsonify(success=True, message="Видео успешно добавлено!")

    except Exception as e:
        logger.error(f"[JSON API] add_video error: {e}", exc_info=True)
        return jsonify(success=False, error=str(e)), 500

# --- Telegram Add Video Command ---
def add_video_command(update, context):
    user = update.message.from_user
    telegram_id = str(user.id)
    role = get_user_role(telegram_id)
    if role not in ['owner', 'admin']:
        update.message.reply_text("❌ You have no rights!")
        return
    text = update.message.text.strip()
    parts = text.split(' ', 2)
    if len(parts) < 3 or parts[1].lower() not in ['moment','trailer','news']:
        update.message.reply_text("❌ Format: /add_video [moment|trailer|news] [title]")
        return
    pending_video_data[telegram_id] = {'content_type': parts[1].lower(), 'title': parts[2]}
    update.message.reply_text(
        f"🎬 Добавление '{parts[1]}' с названием '{parts[2]}'. "
        f"Пришли прямой URL видео (https://...) или отправь видео файлом."
    )

def handle_pending_video_text(update, context):
    user = update.message.from_user
    telegram_id = str(user.id)
    if telegram_id not in pending_video_
        return
    data = pending_video_data.pop(telegram_id)
    content_type, title = data['content_type'], data['title']
    video_url = update.message.text.strip()
    if not (video_url.startswith('http://') or video_url.startswith('https://')):
        update.message.reply_text("❌ Это не URL. Пришли прямую ссылку на видео или отправь файл.")
        pending_video_data[telegram_id] = data
        return
    if content_type == 'moment':
        add_moment(title, "Added via Telegram", video_url)
    elif content_type == 'trailer':
        add_trailer(title, "Added via Telegram", video_url)
    elif content_type == 'news':
        add_news(title, "Added via Telegram", video_url)
    update.message.reply_text(f"✅ '{content_type}' '{title}' добавлено по ссылке!")
    cache_delete('moments_list')
    cache_delete('trailers_list')
    cache_delete('news_list')

# --- ИСПРАВЛЕННЫЙ обработчик файлов ---
def handle_pending_video_file(update, context):
    user = update.message.from_user
    telegram_id = str(user.id)
    logger.info(f"Получен видеофайл от пользователя {telegram_id}")

    if telegram_id not in pending_video_
        logger.debug("Нет ожидающих данных для видео")
        return

    data = pending_video_data.pop(telegram_id)
    content_type, title = data['content_type'], data['title']
    logger.info(f"Обработка {content_type} '{title}'")

    if not update.message.video:
        logger.warning("Полученное сообщение не содержит видео")
        update.message.reply_text("❌ Это не видео. Пришли файл видео или ссылку.")
        pending_video_data[telegram_id] = data
        return

    file_id = update.message.video.file_id
    logger.info(f"Получен file_id: {file_id}")

    # ✅ ИСПРАВЛЕНИЕ: Получаем ПОЛНУЮ прямую ссылку с кэшированием
    # video_url = context.bot.get_file(file_id).file_path # Старый способ - неправильный
    video_url = get_cached_direct_video_url(file_id) # Новый способ - правильный

    if not video_url:
        error_msg = "❌ Не удалось получить прямую ссылку на видео из Telegram"
        logger.error(error_msg)
        update.message.reply_text(error_msg)
        return

    logger.info(f"Сгенерирована прямая ссылка: {video_url[:50]}...")

    # Сохраняем ПОЛНУЮ ссылку
    try:
        if content_type == 'moment':
            add_moment(title, "Added via Telegram", video_url)
        elif content_type == 'trailer':
            add_trailer(title, "Added via Telegram", video_url)
        elif content_type == 'news':
            add_news(title, "Added via Telegram", video_url)

        success_msg = f"✅ '{content_type}' '{title}' добавлено из файла!"
        logger.info(success_msg)
        update.message.reply_text(success_msg)

        cache_delete('moments_list')
        cache_delete('trailers_list')
        cache_delete('news_list')
    except Exception as e:
        error_msg = f"❌ Ошибка сохранения в БД: {e}"
        logger.error(error_msg, exc_info=True) # Добавлено exc_info для полного трейса
        update.message.reply_text(error_msg)


# --- Start Bot ---
def start_bot():
    if updater:
        logger.info("Запуск Telegram бота...")
        updater.start_polling()
        logger.info("Telegram бот запущен и_polling.")
        
        # --- НОВОЕ: Установка Menu Button после запуска ---
        logger.info("Установка Menu Button...")
        try:
            set_menu_button()
            logger.info("Menu Button успешно установлена.")
        except Exception as e:
            logger.error(f"Не удалось установить Menu Button при запуске: {e}")
        # --- КОНЕЦ НОВОГО ---
        
        # updater.idle() блокирует основной поток, что не нужно в Flask приложении
        # updater.idle()

# --- Main ---
if __name__ == '__main__':
    try:
        logger.info("Инициализация базы данных...")
        init_db()
        logger.info("База данных инициализирована.")
    except Exception as e:
        logger.error(f"DB init error: {e}", exc_info=True)
    
    logger.info("Запуск Telegram бота в отдельном потоке...")
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    logger.info("Поток Telegram бота запущен.")
    
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"Запуск Flask приложения на порту {port}...")
    app.run(host='0.0.0.0', port=port)
    logger.info("Flask приложение остановлено.")

# --- Регистрация обработчиков Telegram бота ---
# (Это должно быть в конце файла, после определения всех функций)
if dp:
    # --- ИСПРАВЛЕНО: Добавлен обработчик команды /start ---
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('add_video', add_video_command))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_pending_video_text))
    dp.add_handler(MessageHandler(Filters.video & ~Filters.command, handle_pending_video_file))
