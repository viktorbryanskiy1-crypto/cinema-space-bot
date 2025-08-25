# app.py (Финальная версия с исправлениями)
import os
import threading
import logging
import uuid
import requests
import time
import re
import asyncio
import hashlib
from datetime import datetime
from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, session, send_from_directory, abort, make_response
)
from werkzeug.utils import secure_filename
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, Bot,
    MenuButtonWebApp, Update, InputFile
)
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import redis
import json
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
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://cinema-space-bot.onrender.com').strip().rstrip('/')
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

# --- ИНИЦИАЛИЗАЦИЯ БД ---
try:
    logger.info("Инициализация базы данных...")
    init_db()
    logger.info("✅ База данных инициализирована.")
except Exception as e:
    logger.error(f"❌ ОШИБКА инициализации БД: {e}", exc_info=True)
# --- КОНЕЦ ИНИЦИАЛИЗАЦИИ БД ---

# --- Telegram Bot ---
updater = None
dp = None
pending_video_data = {}

# --- НОВОЕ: Конфигурация кэширования ---
CACHE_CONFIG = {
    'html_expire': 3600,       # Было 1800 (30 минут), стало 1 час
    'api_expire': 120,        # Было 300 (5 минут), стало 2 минуты
    'data_expire': 300,       # Было 600 (10 минут), стало 5 минут
    'static_expire': 2592000, # 30 дней для статики (CSS, JS, изображения)
    'video_url_cache_time': 86400, # Было 21600 (6 часов), стало 24 часа
    'default_expire': 300     # Значение по умолчанию
}

# --- НОВОЕ: Декораторы для кэширования ---
from functools import wraps

def cache_control(max_age):
    """Декоратор для установки заголовков кэширования."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            resp = make_response(f(*args, **kwargs))
            resp.headers['Cache-Control'] = f'public, max-age={max_age}'
            return resp
        return decorated_function
    return decorator

def etag_cache(key_generator_func):
    """Декоратор для кэширования с использованием ETags."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            cache_key_base = key_generator_func(*args, **kwargs)
            cache_key = f"etag_cache_{cache_key_base}"
            cached_data = cache_get(cache_key)
            if cached_data and isinstance(cached_data, dict) and 'html' in cached_data and 'etag' in cached_:
                etag = cached_data['etag']
                if request.headers.get('If-None-Match') == etag:
                    logger.debug(f"ETag совпал для {cache_key_base}, возвращаю 304 Not Modified")
                    return '', 304
            html_content = f(*args, **kwargs)
            etag = hashlib.md5(html_content.encode('utf-8')).hexdigest()
            cache_set(cache_key, {'html': html_content, 'etag': etag}, expire=CACHE_CONFIG['html_expire'])
            resp = make_response(html_content)
            resp.headers['ETag'] = etag
            resp.headers['Cache-Control'] = f'public, max-age={CACHE_CONFIG["html_expire"]}'
            return resp
        return decorated_function
    return decorator
# --- КОНЕЦ новых декораторов ---

# --- УЛУЧШЕННОЕ КЭШИРОВАНИЕ ССЫЛОК С АВТООБНОВЛЕНИЕМ ---
video_url_cache_advanced = {}

def get_cached_direct_video_url_advanced(file_id, cache_time=None):
    """Кэшированное получение прямой ссылки с возможностью автообновления"""
    if cache_time is None:
        cache_time = CACHE_CONFIG['video_url_cache_time']
    current_time = time.time()
    if file_id in video_url_cache_advanced:
        url, expire_time, original_file_id = video_url_cache_advanced[file_id]
        if current_time < expire_time:
            logger.debug(f"Ссылка для file_id {file_id} получена из кэша (осталось {int(expire_time - current_time)} сек)")
            return url, False
        else:
            logger.info(f"Срок действия ссылки для file_id {file_id} истек. Попытка обновления...")
            new_url = get_direct_video_url(original_file_id)
            if new_url:
                video_url_cache_advanced[file_id] = (new_url, current_time + cache_time, original_file_id)
                logger.info(f"Ссылка для file_id {file_id} успешно обновлена")
                return new_url, True
            else:
                logger.warning(f"Не удалось обновить ссылку для file_id {file_id}, возвращаю старую")
                return url, False
    logger.debug(f"Генерация новой ссылки для file_id {file_id}")
    url = get_direct_video_url(file_id)
    if url:
        video_url_cache_advanced[file_id] = (url, current_time + cache_time, file_id)
        logger.debug(f"Ссылка для file_id {file_id} закэширована")
        return url, False
    return None, False

def get_direct_video_url(file_id):
    """Преобразует file_id в прямую ссылку для веба"""
    bot_token = TOKEN
    if not bot_token:
        logger.error("TELEGRAM_TOKEN не установлен для генерации ссылки")
        return None
    try:
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

# --- ИСПРАВЛЕННАЯ Функция для извлечения видео из поста Telegram ---
async def extract_video_url_from_telegram_post(post_url):
    """Извлекает прямую ссылку на видео из поста Telegram."""
    try:
        logger.info(f"[ИЗВЛЕЧЕНИЕ] Попытка извлечь видео из поста: {post_url}")
        post_url = post_url.strip()
        public_match = re.search(r'https?://t\.me/([^/\s]+)/(\d+)', post_url)
        private_match = re.search(r'https?://t.me/c/(\d+)/(\d+)', post_url)
        chat_id_or_username = None
        message_id = None
        if public_match:
            chat_id_or_username = "@" + public_match.group(1)
            message_id = int(public_match.group(2))
            logger.debug(f"[ИЗВЛЕЧЕНИЕ] Найден публичный канал: {chat_id_or_username}, сообщение: {message_id}")
        elif private_match:
            raw_id = int(private_match.group(1))
            chat_id_or_username = -1000000000000 - raw_id
            message_id = int(private_match.group(2))
            logger.debug(f"[ИЗВЛЕЧЕНИЕ] Найден приватный канал (ID): {chat_id_or_username}, сообщение: {message_id}")
        else:
            logger.error(f"[ИЗВЛЕЧЕНИЕ] Неверный формат ссылки на пост: {post_url}")
            return None, "Неверный формат ссылки на пост Telegram."
        if chat_id_or_username is None or message_id is None:
             return None, "Не удалось распарсить ссылку на пост"
        bot = Bot(token=TOKEN)
        YOUR_TEST_CHAT_ID = -1003045387627
        try:
            logger.debug(f"[ИЗВЛЕЧЕНИЕ] Пересылаем сообщение в тестовую группу {YOUR_TEST_CHAT_ID}...")
            forwarded_message = bot.forward_message(
                chat_id=YOUR_TEST_CHAT_ID,
                from_chat_id=chat_id_or_username,
                message_id=message_id
            )
            message = forwarded_message
            logger.info("[ИЗВЛЕЧЕНИЕ] Сообщение успешно получено через forward_message (в тестовую группу)")
        except Exception as e1:
            logger.error(f"[ИЗВЛЕЧЕНИЕ] Не удалось получить сообщение через forward: {e1}")
            return None, "Не удалось получить сообщение. Убедитесь, что бот имеет доступ к сообщению."
        if not message:
            logger.error("[ИЗВЛЕЧЕНИЕ] Сообщение не найдено или бот не имеет доступа")
            return None, "Сообщение не найдено."
        if not message.video:
            logger.error("[ИЗВЛЕЧЕНИЕ] В посте нет видео")
            return None, "В указанном посте не найдено видео."
        file_id = message.video.file_id
        logger.info(f"[ИЗВЛЕЧЕНИЕ] Найден file_id: {file_id}")
        direct_url, _ = get_cached_direct_video_url_advanced(file_id)
        if not direct_url:
            logger.error("[ИЗВЛЕЧЕНИЕ] Не удалось получить прямую ссылку из file_id")
            return None, "Не удалось получить прямую ссылку на видео из Telegram."
        logger.info(f"[ИЗВЛЕЧЕНИЕ] Успешно извлечена прямая ссылка: {direct_url[:50]}...")
        return direct_url, None
    except Exception as e:
        logger.error(f"[ИЗВЛЕЧЕНИЕ] Ошибка извлечения видео из поста {post_url}: {e}", exc_info=True)
        return None, f"Ошибка при обработке ссылки на пост: {str(e)}"

def extract_video_url_sync(post_url):
    """Синхронная обертка для асинхронной функции извлечения видео"""
    try:
        logger.debug("Получение или создание event loop для асинхронного вызова")
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
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

# --- НОВАЯ ФУНКЦИЯ: Извлечение ссылки на изображение из поста Telegram ---
async def extract_image_url_from_telegram_post(post_url):
    """Извлекает прямую ссылку на изображение из поста Telegram."""
    try:
        logger.info(f"[ИЗВЛЕЧЕНИЕ ИЗОБРАЖЕНИЯ] Попытка извлечь изображение из поста: {post_url}")
        post_url = post_url.strip()
        public_match = re.search(r'https?://t\.me/([^/\s]+)/(\d+)', post_url)
        private_match = re.search(r'https?://t.me/c/(\d+)/(\d+)', post_url)
        chat_id_or_username = None
        message_id = None
        if public_match:
            chat_id_or_username = "@" + public_match.group(1)
            message_id = int(public_match.group(2))
            logger.debug(f"[ИЗВЛЕЧЕНИЕ ИЗОБРАЖЕНИЯ] Найден публичный канал: {chat_id_or_username}, сообщение: {message_id}")
        elif private_match:
            raw_id = int(private_match.group(1))
            chat_id_or_username = -1000000000000 - raw_id
            message_id = int(private_match.group(2))
            logger.debug(f"[ИЗВЛЕЧЕНИЕ ИЗОБРАЖЕНИЯ] Найден приватный канал (ID): {chat_id_or_username}, сообщение: {message_id}")
        else:
            logger.error(f"[ИЗВЛЕЧЕНИЕ ИЗОБРАЖЕНИЯ] Неверный формат ссылки на пост: {post_url}")
            return None, "Неверный формат ссылки на пост Telegram."
        if chat_id_or_username is None or message_id is None:
             return None, "Не удалось распарсить ссылку на пост"
        bot = Bot(token=TOKEN)
        YOUR_TEST_CHAT_ID = -1003045387627
        try:
            logger.debug(f"[ИЗВЛЕЧЕНИЕ ИЗОБРАЖЕНИЯ] Пересылаем сообщение в тестовую группу {YOUR_TEST_CHAT_ID}...")
            forwarded_message = bot.forward_message(
                chat_id=YOUR_TEST_CHAT_ID,
                from_chat_id=chat_id_or_username,
                message_id=message_id
            )
            message = forwarded_message
            logger.info("[ИЗВЛЕЧЕНИЕ ИЗОБРАЖЕНИЯ] Сообщение успешно получено через forward_message (в тестовую группу)")
        except Exception as e1:
            logger.error(f"[ИЗВЛЕЧЕНИЕ ИЗОБРАЖЕНИЯ] Не удалось получить сообщение через forward: {e1}")
            return None, "Не удалось получить сообщение. Убедитесь, что бот имеет доступ к сообщению."
        if not message:
            logger.error("[ИЗВЛЕЧЕНИЕ ИЗОБРАЖЕНИЯ] Сообщение не найдено или бот не имеет доступа")
            return None, "Сообщение не найдено."
        if not message.photo:
            logger.error("[ИЗВЛЕЧЕНИЕ ИЗОБРАЖЕНИЯ] В посте нет изображения")
            return None, "В указанном посте не найдено изображение."
        photo_obj = message.photo[-1]
        file_id = photo_obj.file_id
        logger.info(f"[ИЗВЛЕЧЕНИЕ ИЗОБРАЖЕНИЯ] Найден file_id фото: {file_id}")
        direct_url, _ = get_cached_direct_video_url_advanced(file_id)
        if not direct_url:
            logger.error("[ИЗВЛЕЧЕНИЕ ИЗОБРАЖЕНИЯ] Не удалось получить прямую ссылку из file_id")
            return None, "Не удалось получить прямую ссылку на изображение из Telegram."
        logger.info(f"[ИЗВЛЕЧЕНИЕ ИЗОБРАЖЕНИЯ] Успешно извлечена прямая ссылка: {direct_url[:50]}...")
        return direct_url, None
    except Exception as e:
        logger.error(f"[ИЗВЛЕЧЕНИЕ ИЗОБРАЖЕНИЯ] Ошибка извлечения изображения из поста {post_url}: {e}", exc_info=True)
        return None, f"Ошибка при обработке ссылки на пост: {str(e)}"

def extract_image_url_sync(post_url):
    """Синхронная обертка для асинхронной функции извлечения изображения."""
    try:
        logger.debug("Получение или создание event loop для асинхронного вызова extract_image_url_from_telegram_post")
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            logger.debug("Создание нового event loop")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        logger.debug("Запуск асинхронной функции extract_image_url_from_telegram_post")
        result = loop.run_until_complete(extract_image_url_from_telegram_post(post_url))
        logger.debug(f"Асинхронная функция extract_image_url_from_telegram_post завершена, результат: {result}")
        return result
    except Exception as e:
        logger.error(f"Ошибка в синхронной обертке extract_image_url_sync: {e}", exc_info=True)
        return None, f"Ошибка обработки запроса: {e}"

# --- НОВАЯ ФУНКЦИЯ: Обновление устаревшей ссылки ---
@app.route('/api/refresh_video_url', methods=['POST'])
def refresh_video_url():
    """Обновляет устаревшую ссылку на видео по Telegram посту"""
    try:
        data = request.get_json()
        if not data:
            logger.warning("[ОБНОВЛЕНИЕ ССЫЛКИ] Неверный формат данных")
            return jsonify(success=False, error="Неверный формат данных"), 400
        post_url = data.get('post_url', '').strip()
        if not post_url:
            logger.warning("[ОБНОВЛЕНИЕ ССЫЛКИ] Не указана ссылка на пост")
            return jsonify(success=False, error="Не указана ссылка на пост"), 400
        logger.info(f"[ОБНОВЛЕНИЕ ССЫЛКИ] Запрошено обновление для ссылки: {post_url[:50]}...")
        direct_url, error = extract_video_url_sync(post_url)
        if direct_url:
            logger.info(f"[ОБНОВЛЕНИЕ ССЫЛКИ] Новая ссылка успешно получена")
            return jsonify(success=True, new_url=direct_url)
        else:
            logger.error(f"[ОБНОВЛЕНИЕ ССЫЛКИ] Ошибка при извлечении: {error}")
            return jsonify(success=False, error=error), 400
    except Exception as e:
        logger.error(f"[ОБНОВЛЕНИЕ ССЫЛКИ] Критическая ошибка: {e}", exc_info=True)
        return jsonify(success=False, error="Внутренняя ошибка сервера"), 500

# --- ИЗМЕНЕННАЯ ФУНКЦИЯ: Кэширование HTML страниц с учетом ETag ---
def get_cached_html(key, generate_func, expire=None):
    """Получает HTML из кэша или генерирует новый, используя ETag."""
    if expire is None:
        expire = CACHE_CONFIG['html_expire']
    etag_cache_key = f"etag_cache_{key}"
    cached_data = cache_get(etag_cache_key)
    if cached_data and isinstance(cached_data, dict) and 'html' in cached_data and 'etag' in cached_:
        logger.info(f"HTML для {key} получен из кэша (с ETag)")
        return cached_data['html']
    html = generate_func()
    if html:
        etag = hashlib.md5(html.encode('utf-8')).hexdigest()
        cache_set(etag_cache_key, {'html': html, 'etag': etag}, expire=expire)
        logger.info(f"HTML для {key} закэширован на {expire} секунд (с ETag)")
    return html

# --- Функция для установки Menu Button ---
def set_menu_button():
    """Устанавливает кнопку меню для бота"""
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN не установлен для установки Menu Button")
        return False
    try:
        logger.info("Начало выполнения set_menu_button")
        bot = Bot(token=TOKEN)
        logger.info("Объект Bot создан")
        app_url = f"{WEBHOOK_URL}/?mode=fullscreen"
        logger.info(f"URL для Menu Button: {app_url}")
        menu_button = MenuButtonWebApp(
            text="movies",
            web_app=WebAppInfo(url=app_url)
        )
        logger.info("Объект MenuButtonWebApp создан")
        bot.set_chat_menu_button(menu_button=menu_button)
        logger.info(f"✅ Menu Button установлена: {app_url}")
        return True
    except Exception as e:
        logger.error(f"❌ ОШИБКА в set_menu_button: {e}", exc_info=True)
        return False

if TOKEN:
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    def start(update, context):
        try:
            logger.info("Обработчик /start ВЫЗВАН")
            user = update.message.from_user
            logger.info(f"Получен user: {user}")
            telegram_id = str(user.id)
            logger.info(f"Telegram ID: {telegram_id}")
            logger.info("Вызов get_or_create_user...")
            get_or_create_user(
                telegram_id=telegram_id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
            logger.info("get_or_create_user выполнен")
            app_url = f"{WEBHOOK_URL}/?mode=fullscreen"
            logger.info(f"Сформированный URL кнопки: {app_url}")
            keyboard = [[
                InlineKeyboardButton(
                    "🌌 КиноВселенная",
                    web_app=WebAppInfo(url=app_url)
                )
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            logger.info("Отправка сообщения пользователю...")
            update.message.reply_text(
                "🚀 Добро пожаловать в КиноВселенную!\n"
                "✨ Исследуй космос кино\n"
                "🎬 Лучшие моменты из фильмов\n"
                "🎥 Свежие трейлеры\n"
                "📰 Горячие новости\n"
                "Нажми кнопку для входа в приложение",
                reply_markup=reply_markup
            )
            logger.info("Сообщение отправлено успешно")
        except Exception as e:
            logger.error(f"КРИТИЧЕСКАЯ ОШИБКА в обработчике /start: {e}", exc_info=True)
    def menu_command(update, context):
        try:
            success = set_menu_button()
            if success:
                update.message.reply_text("✅ Кнопка меню успешно установлена/обновлена!")
            else:
                update.message.reply_text("❌ Ошибка установки кнопки меню")
        except Exception as e:
            logger.error(f"Ошибка в /menu: {e}")
            update.message.reply_text("❌ Ошибка при установке кнопки меню")

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
    if not redis_client:
        return None
    try:
        raw = redis_client.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None

def cache_set(key, value, expire=300):
    if redis_client:
        try:
            actual_expire = expire if expire > 0 else CACHE_CONFIG.get('default_expire', 300)
            redis_client.set(key, json.dumps(value), ex=actual_expire)
        except Exception as e:
            logger.warning(f"Ошибка сохранения в Redis: {e}")

def cache_delete(key):
    if redis_client:
        try:
            redis_client.delete(key)
        except Exception:
            pass

# --- НОВОЕ: Функция для инвалидации ETag кэша ---
def invalidate_etag_cache(cache_key_base):
    """Удаляет кэш ETag для заданного ключа."""
    cache_key = f"etag_cache_{cache_key_base}"
    cache_delete(cache_key)
    logger.debug(f"Кэш ETag для '{cache_key_base}' инвалидирован.")
# --- КОНЕЦ НОВОГО ---

def build_extra_map(data, item_type_plural):
    """Добавляет реакции и комментарии к каждому элементу данных."""
    extra = {}
    for row in data:
        item_id = row[0]
        reactions_cache_key = f"reactions_{item_type_plural}_{item_id}"
        reactions = cache_get(reactions_cache_key)
        if reactions is None:
            reactions = get_reactions_count(item_type_plural, item_id) or {'like': 0, 'dislike': 0, 'star': 0, 'fire': 0}
            cache_set(reactions_cache_key, reactions, expire=CACHE_CONFIG['data_expire'])
        comments_cache_key = f"comments_{item_type_plural}_{item_id}"
        comments = cache_get(comments_cache_key)
        if comments is None:
            comments = get_comments(item_type_plural, item_id) or []
            cache_set(comments_cache_key, comments, expire=CACHE_CONFIG['data_expire'])
        extra[item_id] = {'reactions': reactions, 'comments_count': len(comments)}
    return extra

# --- Routes (пользовательские) ---
@app.route('/')
@cache_control(CACHE_CONFIG['html_expire'])
def index():
    return render_template('index.html')

# --- НОВЫЙ МАРШРУТ ДЛЯ ПОИСКА ПО ССЫЛКЕ ---
@app.route('/search_by_link')
@cache_control(CACHE_CONFIG['html_expire'])
def search_by_link_page():
    """Отображает страницу поиска фильма по ссылке."""
    return render_template('search_by_link.html')
# --- КОНЕЦ НОВОГО МАРШРУТА ---

# --- ИЗМЕНЕННЫЕ: Кэшированные маршруты для вкладок с ETag ---
def moments_page_key():
    return "moments_page"

@app.route('/moments')
@etag_cache(moments_page_key)
def moments():
    def generate_moments_html():
        try:
            logger.info("Запрос к /moments")
            data = get_all_moments() or []
            logger.info(f"Получено {len(data)} моментов из БД")
            extra_map = build_extra_map(data, 'moments')
            combined_data = []
            for row in data:
                item_id = row[0]
                item_dict = {
                    'id': row[0],
                    'title': row[1] if len(row) > 1 else '',
                    'description': row[2] if len(row) > 2 else '',
                    'video_url': row[3] if len(row) > 3 else '',
                    'preview_url': row[4] if len(row) > 4 else '',
                    'created_at': row[5] if len(row) > 5 else None
                }
                extra_info = extra_map.get(item_id, {'reactions': {'like': 0, 'dislike': 0, 'star': 0, 'fire': 0}, 'comments_count': 0})
                if isinstance(extra_info.get('reactions'), dict):
                    item_dict['reactions'] = extra_info['reactions']
                else:
                    item_dict['reactions'] = {'like': 0, 'dislike': 0, 'star': 0, 'fire': 0}
                item_dict['comments_count'] = extra_info.get('comments_count', 0)
                combined_data.append(item_dict)
            logger.info("Данные объединены успешно")
            return render_template('moments.html', moments=combined_data)
        except Exception as e:
            logger.error(f"API add_moment error: {e}", exc_info=True)
            return render_template('error.html', error=str(e))
    return generate_moments_html()

def trailers_page_key():
    return "trailers_page"

@app.route('/trailers')
@etag_cache(trailers_page_key)
def trailers():
    def generate_trailers_html():
        try:
            logger.info("Запрос к /trailers")
            data = get_all_trailers() or []
            logger.info(f"Получено {len(data)} трейлеров из БД")
            extra_map = build_extra_map(data, 'trailers')
            combined_data = []
            for row in data:
                item_id = row[0]
                item_dict = {
                    'id': row[0],
                    'title': row[1] if len(row) > 1 else '',
                    'description': row[2] if len(row) > 2 else '',
                    'video_url': row[3] if len(row) > 3 else '',
                    'preview_url': row[4] if len(row) > 4 else '',
                    'created_at': row[5] if len(row) > 5 else None
                }
                extra_info = extra_map.get(item_id, {'reactions': {'like': 0, 'dislike': 0, 'star': 0, 'fire': 0}, 'comments_count': 0})
                if isinstance(extra_info.get('reactions'), dict):
                    item_dict['reactions'] = extra_info['reactions']
                else:
                    item_dict['reactions'] = {'like': 0, 'dislike': 0, 'star': 0, 'fire': 0}
                item_dict['comments_count'] = extra_info.get('comments_count', 0)
                combined_data.append(item_dict)
            logger.info("Данные объединены успешно")
            return render_template('trailers.html', trailers=combined_data)
        except Exception as e:
            logger.error(f"API add_trailer error: {e}", exc_info=True)
            return render_template('error.html', error=str(e))
    return generate_trailers_html()

def news_page_key():
    return "news_page"

@app.route('/news')
@etag_cache(news_page_key)
def news():
    def generate_news_html():
        try:
            logger.info("Запрос к /news")
            data = get_all_news() or []
            logger.info(f"Получено {len(data)} новостей из БД")
            extra_map = build_extra_map(data, 'news')
            combined_data = []
            for row in data:
                item_id = row[0]
                item_dict = {
                    'id': row[0],
                    'title': row[1] if len(row) > 1 else '',
                    'text': row[2] if len(row) > 2 else '',
                    'image_url': row[3] if len(row) > 3 else '',
                    'created_at': row[4] if len(row) > 4 else None
                }
                extra_info = extra_map.get(item_id, {'reactions': {'like': 0, 'dislike': 0, 'star': 0, 'fire': 0}, 'comments_count': 0})
                if isinstance(extra_info.get('reactions'), dict):
                    item_dict['reactions'] = extra_info['reactions']
                else:
                    item_dict['reactions'] = {'like': 0, 'dislike': 0, 'star': 0, 'fire': 0}
                item_dict['comments_count'] = extra_info.get('comments_count', 0)
                combined_data.append(item_dict)
            logger.info("Данные объединены успешно")
            return render_template('news.html', news=combined_data)
        except Exception as e:
            logger.error(f"API add_news error: {e}", exc_info=True)
            return render_template('error.html', error=str(e))
    return generate_news_html()

# --- ИЗМЕНЕННЫЕ: Маршруты для отдельных элементов с кэшированием данных ---
@app.route('/moments/<int:item_id>')
@cache_control(CACHE_CONFIG['html_expire'])
def moment_detail(item_id):
    """Отображает страницу одного момента."""
    logger.info(f"Запрос к /moments/{item_id}")
    item_cache_key = f"item_moments_{item_id}"
    item = cache_get(item_cache_key)
    if not item:
        item = get_item_by_id('moments', item_id)
        if item:
             cache_set(item_cache_key, item, expire=CACHE_CONFIG['data_expire'])
    if not item:
        logger.warning(f"Момент с id={item_id} не найден")
        abort(404)
    reactions_cache_key = f"reactions_moments_{item_id}"
    reactions = cache_get(reactions_cache_key)
    if reactions is None:
        reactions = get_reactions_count('moments', item_id)
        cache_set(reactions_cache_key, reactions, expire=CACHE_CONFIG['data_expire'])
    comments_cache_key = f"comments_moments_{item_id}"
    comments = cache_get(comments_cache_key)
    if comments is None:
        comments = get_comments('moments', item_id)
        cache_set(comments_cache_key, comments, expire=CACHE_CONFIG['data_expire'])
    logger.info(f"Момент {item_id} найден: {item[1] if len(item) > 1 else 'Без названия'}")
    item_dict = {
        'id': item[0],
        'title': item[1] if len(item) > 1 else '',
        'description': item[2] if len(item) > 2 else '',
        'video_url': item[3] if len(item) > 3 else '',
        'preview_url': item[4] if len(item) > 4 else '',
        'created_at': item[5] if len(item) > 5 else None
    }
    return render_template('moment_detail.html', item=item_dict, reactions=reactions, comments=comments)

# Аналогично для трейлеров и новостей
@app.route('/trailers/<int:item_id>')
@cache_control(CACHE_CONFIG['html_expire'])
def trailer_detail(item_id):
    """Отображает страницу одного трейлера."""
    logger.info(f"Запрос к /trailers/{item_id}")
    item_cache_key = f"item_trailers_{item_id}"
    item = cache_get(item_cache_key)
    if not item:
        item = get_item_by_id('trailers', item_id)
        if item:
             cache_set(item_cache_key, item, expire=CACHE_CONFIG['data_expire'])
    if not item:
        logger.warning(f"Трейлер с id={item_id} не найден")
        abort(404)
    reactions_cache_key = f"reactions_trailers_{item_id}"
    reactions = cache_get(reactions_cache_key)
    if reactions is None:
        reactions = get_reactions_count('trailers', item_id)
        cache_set(reactions_cache_key, reactions, expire=CACHE_CONFIG['data_expire'])
    comments_cache_key = f"comments_trailers_{item_id}"
    comments = cache_get(comments_cache_key)
    if comments is None:
        comments = get_comments('trailers', item_id)
        cache_set(comments_cache_key, comments, expire=CACHE_CONFIG['data_expire'])
    logger.info(f"Трейлер {item_id} найден: {item[1] if len(item) > 1 else 'Без названия'}")
    item_dict = {
        'id': item[0],
        'title': item[1] if len(item) > 1 else '',
        'description': item[2] if len(item) > 2 else '',
        'video_url': item[3] if len(item) > 3 else '',
        'preview_url': item[4] if len(item) > 4 else '',
        'created_at': item[5] if len(item) > 5 else None
    }
    return render_template('trailer_detail.html', item=item_dict, reactions=reactions, comments=comments)

@app.route('/news/<int:item_id>')
@cache_control(CACHE_CONFIG['html_expire'])
def news_detail(item_id):
    """Отображает страницу одной новости."""
    logger.info(f"Запрос к /news/{item_id}")
    item_cache_key = f"item_news_{item_id}"
    item = cache_get(item_cache_key)
    if not item:
        item = get_item_by_id('news', item_id)
        if item:
             cache_set(item_cache_key, item, expire=CACHE_CONFIG['data_expire'])
    if not item:
        logger.warning(f"Новость с id={item_id} не найдена")
        abort(404)
    reactions_cache_key = f"reactions_news_{item_id}"
    reactions = cache_get(reactions_cache_key)
    if reactions is None:
        reactions = get_reactions_count('news', item_id)
        cache_set(reactions_cache_key, reactions, expire=CACHE_CONFIG['data_expire'])
    comments_cache_key = f"comments_news_{item_id}"
    comments = cache_get(comments_cache_key)
    if comments is None:
        comments = get_comments('news', item_id)
        cache_set(comments_cache_key, comments, expire=CACHE_CONFIG['data_expire'])
    logger.info(f"Новость {item_id} найдена: {item[1] if len(item) > 1 else 'Без заголовка'}")
    item_dict = {
        'id': item[0],
        'title': item[1] if len(item) > 1 else '',
        'text': item[2] if len(item) > 2 else '',
        'image_url': item[3] if len(item) > 3 else '',
        'created_at': item[4] if len(item) > 4 else None
    }
    return render_template('news_detail.html', item=item_dict, reactions=reactions, comments=comments)

# --- ИЗМЕНЕННЫЕ: API-эндпоинты с кэшированием ---
@app.route('/api/comments', methods=['GET'])
def api_get_comments():
    try:
        item_type = request.args.get('type')
        item_id = int(request.args.get('id'))
        cache_key = f"api_comments_{item_type}_{item_id}"
        cached_comments = cache_get(cache_key)
        if cached_comments is not None:
            logger.debug(f"Комментарии для {item_type}/{item_id} получены из кэша")
            return jsonify(comments=cached_comments)
        comments = get_comments(item_type, item_id)
        cache_set(cache_key, comments, expire=CACHE_CONFIG['api_expire'])
        logger.debug(f"Комментарии для {item_type}/{item_id} получены из БД и закэшированы")
        return jsonify(comments=comments)
    except Exception as e:
        logger.error(f"API get_comments error: {e}", exc_info=True)
        return jsonify(comments=[], error=str(e)), 500

# Добавим GET для получения реакций по типу и ID
@app.route('/api/reactions/<item_type>/<int:item_id>', methods=['GET'])
def api_get_reactions(item_type, item_id):
    try:
        cache_key = f"api_reactions_{item_type}_{item_id}"
        cached_reactions = cache_get(cache_key)
        if cached_reactions is not None:
            logger.debug(f"Реакции для {item_type}/{item_id} получены из кэша")
            return jsonify(reactions=cached_reactions)
        reactions = get_reactions_count(item_type, item_id)
        cache_set(cache_key, reactions, expire=CACHE_CONFIG['api_expire'])
        logger.debug(f"Реакции для {item_type}/{item_id} получены из БД и закэшированы")
        return jsonify(reactions=reactions)
    except Exception as e:
        logger.error(f"API get_reactions error: {e}", exc_info=True)
        return jsonify(reactions={}, error=str(e)), 500

# --- ИЗМЕНЕННЫЙ: Маршрут для отдачи статических файлов с кэшированием ---
@app.route('/uploads/<filename>')
@cache_control(CACHE_CONFIG['static_expire'])
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/static/<path:filename>')
@cache_control(CACHE_CONFIG['static_expire'])
def static_files(filename):
    return send_from_directory('static', filename)

# --- Маршрут для Webhook от Telegram ---
@app.route('/<string:token>', methods=['POST'])
def telegram_webhook(token):
    if token != TOKEN:
        logger.warning(f"Получен запрос webhook с неверным токеном: {token}")
        return jsonify({'error': 'Unauthorized'}), 403
    try:
        json_string = request.get_data().decode('utf-8')
        logger.debug(f"Получено обновление webhook: {json_string[:200]}...")
        update = Update.de_json(json.loads(json_string), updater.bot)
        updater.dispatcher.process_update(update)
        logger.info("Обновление из webhook обработано")
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        logger.error(f"Ошибка обработки webhook обновления: {e}", exc_info=True)
        return jsonify({'error': 'Internal Server Error'}), 500

# --- Маршрут для проверки webhook ---
@app.route('/webhook-info')
def webhook_info():
    if not TOKEN:
        return jsonify({'error': 'TELEGRAM_TOKEN not set'}), 500
    try:
        bot = Bot(token=TOKEN)
        info = bot.get_webhook_info()
        return jsonify(info.to_dict())
    except Exception as e:
        logger.error(f"Ошибка получения информации о webhook: {e}")
        return jsonify({'error': str(e)}), 500

# --- Вспомогательная функция для получения данных из формы или JSON ---
def _get_payload():
    """Получает данные из формы или JSON в зависимости от типа запроса."""
    if request.is_json:
        return request.get_json()
    else:
        return request.form.to_dict()

# --- ИЗМЕНЕННЫЕ: Маршруты API добавления контента с инвалидацией кэша ---
@app.route('/api/add_moment', methods=['POST'])
def api_add_moment():
    try:
        payload = _get_payload()
        title = payload.get('title', '').strip()
        desc = payload.get('description', '').strip()
        video_url = payload.get('video_url', '').strip()
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
            if saved:
                video_url = saved
        if not video_url:
            logger.error("Не указан video_url, не извлечен из поста и не загружен файл")
            return jsonify(success=False, error="Укажите ссылку на видео, пост Telegram или загрузите файл"), 400
        add_moment(title, desc, video_url)
        # --- ИНВАЛИДАЦИЯ КЭША ---
        cache_delete('moments_list')
        cache_delete('moments_page')
        # --- НОВОЕ: Инвалидация кэша ETag ---
        invalidate_etag_cache('moments_page')
        # --- КОНЕЦ ИНВАЛИДАЦИИ ---
        logger.info(f"Добавлен момент: {title}")
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"API add_moment error: {e}", exc_info=True)
        return jsonify(success=False, error=str(e)), 500

@app.route('/api/add_trailer', methods=['POST'])
def api_add_trailer():
    try:
        payload = _get_payload()
        title = payload.get('title', '').strip()
        desc = payload.get('description', '').strip()
        video_url = payload.get('video_url', '').strip()
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
            if saved:
                video_url = saved
        if not video_url:
            logger.error("Не указан video_url, не извлечен из поста и не загружен файл")
            return jsonify(success=False, error="Укажите ссылку на видео, пост Telegram или загрузите файл"), 400
        add_trailer(title, desc, video_url)
        # --- ИНВАЛИДАЦИЯ КЭША ---
        cache_delete('trailers_list')
        cache_delete('trailers_page')
        # --- НОВОЕ: Инвалидация кэша ETag ---
        invalidate_etag_cache('trailers_page')
        # --- КОНЕЦ ИНВАЛИДАЦИИ ---
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
        text = payload.get('text', payload.get('description', '')).strip()
        image_url = payload.get('image_url', '').strip()
        if not image_url and 'image_file' in request.files:
            saved = save_uploaded_file(request.files['image_file'], ALLOWED_IMAGE_EXTENSIONS)
            if saved:
                image_url = saved
        add_news(title, text, image_url)
        # --- ИНВАЛИДАЦИЯ КЭША ---
        cache_delete('news_list')
        cache_delete('news_page')
        # --- НОВОЕ: Инвалидация кэша ETag ---
        invalidate_etag_cache('news_page')
        # --- КОНЕЦ ИНВАЛИДАЦИИ ---
        logger.info(f"Добавлена новость: {title}")
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"API add_news error: {e}", exc_info=True)
        return jsonify(success=False, error=str(e)), 500

# --- ИЗМЕНЕННЫЙ: Маршрут API добавления комментария с инвалидацией кэша ---
@app.route('/api/comment', methods=['POST'])
def api_add_comment():
    try:
        data = request.get_json(force=True)
        item_type = data.get('item_type')
        item_id = int(data.get('item_id'))
        user_name = data.get('user_name', 'Гость')
        text = data.get('text')
        add_comment(item_type, item_id, user_name, text)
        # --- ИНВАЛИДАЦИЯ КЭША ---
        cache_delete(f"api_comments_{item_type}_{item_id}")
        cache_delete(f"comments_{item_type}_{item_id}")
        cache_delete(f"{item_type}s_page")
        # --- НОВОЕ: Инвалидация кэша ETag для страницы списка ---
        invalidate_etag_cache(f"{item_type}s_page")
        # --- КОНЕЦ ИНВАЛИДАЦИИ ---
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"API add_comment error: {e}", exc_info=True)
        return jsonify(success=False, error=str(e)), 500

# --- ИЗМЕНЕННЫЙ: Маршрут API добавления реакции с инвалидацией кэша ---
@app.route('/api/reaction', methods=['GET'])
def api_get_reaction():
    item_type = request.args.get('type')
    item_id = request.args.get('id')
    if item_type and item_id:
        return api_get_reactions(item_type, int(item_id))
    else:
        return jsonify(reactions={}, error="Не указаны type или id"), 400

@app.route('/api/reaction', methods=['POST'])
def api_add_reaction_post():
    try:
        data = request.get_json(force=True)
        item_type = data.get('item_type')
        item_id = int(data.get('item_id'))
        user_id = data.get('user_id', 'anonymous')
        reaction = data.get('reaction')
        success = add_reaction(item_type, item_id, user_id, reaction)
        if success:
            # --- ИНВАЛИДАЦИЯ КЭША ---
            cache_delete(f"api_reactions_{item_type}_{item_id}")
            cache_delete(f"reactions_{item_type}_{item_id}")
            cache_delete(f"{item_type}s_page")
            # --- НОВОЕ: Инвалидация кэша ETag для страницы списка ---
            invalidate_etag_cache(f"{item_type}s_page")
            # --- КОНЕЦ ИНВАЛИДАЦИИ ---
        return jsonify(success=success)
    except Exception as e:
        logger.error(f"API add_reaction error: {e}", exc_info=True)
        return jsonify(success=False, error=str(e)), 500

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
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

# --- ИСПРАВЛЕННЫЙ И ОБНОВЛЕННЫЙ МАРШРУТ ДЛЯ ДОБАВЛЕНИЯ КОНТЕНТА ЧЕРЕЗ АДМИНКУ С ПОДДЕРЖКОЙ ПРЕВЬЮ ---
@app.route('/admin/add_content', methods=['GET', 'POST'])
@admin_required
def admin_add_content():
    """Отображает форму добавления контента и обрабатывает её."""
    if request.method == 'POST':
        try:
            content_type = request.form.get('content_type', '').strip()
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            telegram_url = request.form.get('telegram_url', '').strip()
            # --- НОВОЕ: Получаем данные превью ---
            preview_telegram_url = request.form.get('preview_telegram_url', '').strip()
            preview_url_for_content = None
            content_url = None
            # --- Приоритет 1: Ссылка на Telegram для видео ---
            if telegram_url:
                logger.info(f"[ADMIN FORM] Обнаружена ссылка на Telegram пост: {telegram_url}")
                if 't.me/' not in telegram_url:
                     return render_template('admin/add_content.html', error="Ссылка должна вести на пост в Telegram (t.me/...)")
                direct_url, error = extract_video_url_sync(telegram_url)
                if direct_url:
                    content_url = direct_url
                    logger.info(f"[ADMIN FORM] Извлечена прямая ссылка на видео из поста: {content_url[:50]}...")
                else:
                    logger.error(f"[ADMIN FORM] Ошибка извлечения видео из поста: {error}")
                    return render_template('admin/add_content.html', error=error)
            # --- Приоритет 2: Загруженный файл видео ---
            elif 'video_file' in request.files:
                file = request.files['video_file']
                if file and file.filename != '':
                    try:
                        YOUR_TEST_CHAT_ID = -1003045387627
                        from telegram import Bot
                        bot = Bot(token=TOKEN)
                        file.stream.seek(0)
                        input_file = InputFile(file.stream, filename=file.filename)
                        logger.info(f"[ADMIN FORM] Отправка видео '{file.filename}' в Telegram (чат {YOUR_TEST_CHAT_ID})...")
                        sent_message = bot.send_video(chat_id=YOUR_TEST_CHAT_ID, video=input_file, supports_streaming=True)
                        if sent_message and sent_message.video:
                            new_file_id = sent_message.video.file_id
                            logger.info(f"[ADMIN FORM] Видео загружено в Telegram, file_id: {new_file_id}")
                            direct_url, _ = get_cached_direct_video_url_advanced(new_file_id)
                            if direct_url:
                                content_url = direct_url
                                logger.info(f"[ADMIN FORM] Получена прямая ссылка на видео из Telegram: {content_url[:50]}...")
                            else:
                                logger.error("[ADMIN FORM] Не удалось получить прямую ссылку для загруженного видео")
                                return render_template('admin/add_content.html', error="Ошибка получения ссылки на загруженное видео.")
                        else:
                            logger.error("[ADMIN FORM] Не удалось отправить видео в Telegram или получить file_id")
                            return render_template('admin/add_content.html', error="Ошибка отправки видео в Telegram.")
                    except Exception as e:
                        logger.error(f"[ADMIN FORM] Ошибка при работе с Telegram API для загрузки видео: {e}", exc_info=True)
                        return render_template('admin/add_content.html', error=f"Ошибка обработки видео: {e}")
            # --- Проверка: был ли определен URL/путь к видео ---
            if not content_url:
                return render_template('admin/add_content.html', error="Укажите ссылку на Telegram пост с видео или загрузите видео файл.")
            # --- НОВОЕ: Обработка превью ---
            # Приоритет 1: Ссылка на пост Telegram с превью
            if preview_telegram_url:
                logger.info(f"[ADMIN FORM] Обнаружена ссылка на Telegram пост с превью: {preview_telegram_url}")
                if 't.me/' not in preview_telegram_url:
                    logger.warning("[ADMIN FORM] Неверный формат ссылки на превью. Продолжаем без превью.")
                else:
                    direct_preview_url, error_p = extract_image_url_sync(preview_telegram_url)
                    if direct_preview_url:
                        preview_url_for_content = direct_preview_url
                        logger.info(f"[ADMIN FORM] Извлечена прямая ссылка на превью из поста: {preview_url_for_content[:50]}...")
                    else:
                        logger.error(f"[ADMIN FORM] Ошибка извлечения превью из поста: {error_p}")
            # Приоритет 2: Загруженный файл превью
            elif 'preview_file' in request.files:
                preview_file = request.files['preview_file']
                if preview_file and preview_file.filename != '':
                    try:
                        YOUR_TEST_CHAT_ID = -1003045387627
                        from telegram import Bot
                        bot = Bot(token=TOKEN)
                        preview_file.stream.seek(0)
                        input_file = InputFile(preview_file.stream, filename=preview_file.filename)
                        logger.info(f"[ADMIN FORM] Отправка превью '{preview_file.filename}' в Telegram (чат {YOUR_TEST_CHAT_ID})...")
                        sent_message = bot.send_photo(chat_id=YOUR_TEST_CHAT_ID, photo=input_file)
                        if sent_message and sent_message.photo:
                            photo_obj = sent_message.photo[-1]
                            new_file_id = photo_obj.file_id
                            logger.info(f"[ADMIN FORM] Превью загружено в Telegram, file_id: {new_file_id}")
                            direct_preview_url, _ = get_cached_direct_video_url_advanced(new_file_id)
                            if direct_preview_url:
                                preview_url_for_content = direct_preview_url
                                logger.info(f"[ADMIN FORM] Получена прямая ссылка на превью из Telegram: {preview_url_for_content[:50]}...")
                            else:
                                logger.error("[ADMIN FORM] Не удалось получить прямую ссылку для загруженного превью")
                        else:
                            logger.error("[ADMIN FORM] Не удалось отправить превью в Telegram или получить file_id")
                    except Exception as e:
                        logger.error(f"[ADMIN FORM] Ошибка при работе с Telegram API для загрузки превью: {e}", exc_info=True)
            # --- КОНЕЦ ОБРАБОТКИ ПРЕВЬЮ ---
            # --- Сохранение в БД ---
            if content_type == 'moment':
                add_moment(title, description, content_url, preview_url_for_content)
                # --- ИНВАЛИДАЦИЯ КЭША ---
                cache_delete('moments_list')
                cache_delete('moments_page')
                invalidate_etag_cache('moments_page')
                # --- КОНЕЦ ИНВАЛИДАЦИИ ---
                logger.info(f"[ADMIN FORM] Добавлен момент: {title}")
            elif content_type == 'trailer':
                add_trailer(title, description, content_url, preview_url_for_content)
                # --- ИНВАЛИДАЦИЯ КЭША ---
                cache_delete('trailers_list')
                cache_delete('trailers_page')
                invalidate_etag_cache('trailers_page')
                # --- КОНЕЦ ИНВАЛИДАЦИИ ---
                logger.info(f"[ADMIN FORM] Добавлен трейлер: {title}")
            elif content_type == 'news':
                add_news(title, description, content_url)
                # --- ИНВАЛИДАЦИЯ КЭША ---
                cache_delete('news_list')
                cache_delete('news_page')
                invalidate_etag_cache('news_page')
                # --- КОНЕЦ ИНВАЛИДАЦИИ ---
                logger.info(f"[ADMIN FORM] Добавлена новость: {title}")
            else:
                return render_template('admin/add_content.html', error="Неверный тип контента.")
            return redirect(url_for('admin_content'))
        except Exception as e:
            logger.error(f"[ADMIN FORM] add_content error: {e}", exc_info=True)
            return render_template('admin/add_content.html', error=f"Ошибка сервера: {e}")
    return render_template('admin/add_content.html')

# --- КОНЕЦ ИСПРАВЛЕННОГО И ОБНОВЛЕННОГО МАРШРУТА ---
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
        delete_moment(content_id)
        # --- ИНВАЛИДАЦИЯ КЭША ---
        cache_delete('moments_list')
        cache_delete('moments_page')
        invalidate_etag_cache('moments_page')
        # --- КОНЕЦ ИНВАЛИДАЦИИ ---
    elif content_type == 'trailer':
        delete_trailer(content_id)
        # --- ИНВАЛИДАЦИЯ КЭША ---
        cache_delete('trailers_list')
        cache_delete('trailers_page')
        invalidate_etag_cache('trailers_page')
        # --- КОНЕЦ ИНВАЛИДАЦИИ ---
    elif content_type == 'news':
        delete_news(content_id)
        # --- ИНВАЛИДАЦИЯ КЭША ---
        cache_delete('news_list')
        cache_delete('news_page')
        invalidate_etag_cache('news_page')
        # --- КОНЕЦ ИНВАЛИДАЦИИ ---
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

@app.route('/admin/add_video_json', methods=['POST'])
@admin_required
def admin_add_video_json():
    """API endpoint для добавления видео через форму add_video.html"""
    try:
        data = request.get_json()
        if not data:
            return jsonify(success=False, error="Неверный формат данных (ожидается JSON)"), 400
        title = data.get('title', '').strip()
        description = data.get('description', '').strip()
        category = data.get('category', '').strip()
        post_link = data.get('post_link', '').strip()
        if not title or not post_link or not category:
            return jsonify(success=False, error="Заполните все обязательные поля"), 400
        if category not in ['moment', 'trailer', 'news']:
            return jsonify(success=False, error="Неверный тип контента"), 400
        video_url = post_link
        if 't.me/' in post_link:
            logger.info(f"[JSON API] Обнаружена ссылка на Telegram пост: {post_link}")
            direct_url, error = extract_video_url_sync(post_link)
            if direct_url:
                video_url = direct_url
                logger.info(f"[JSON API] Извлечена прямая ссылка из поста: {video_url[:50]}...")
            else:
                logger.error(f"[JSON API] Ошибка извлечения видео из поста: {error}")
                return jsonify(success=False, error=error), 400
        if category == 'moment':
            add_moment(title, description, video_url)
            # --- ИНВАЛИДАЦИЯ КЭША ---
            cache_delete('moments_list')
            cache_delete('moments_page')
            invalidate_etag_cache('moments_page')
            # --- КОНЕЦ ИНВАЛИДАЦИИ ---
        elif category == 'trailer':
            add_trailer(title, description, video_url)
            # --- ИНВАЛИДАЦИЯ КЭША ---
            cache_delete('trailers_list')
            cache_delete('trailers_page')
            invalidate_etag_cache('trailers_page')
            # --- КОНЕЦ ИНВАЛИДАЦИИ ---
        elif category == 'news':
            add_news(title, description, video_url if video_url.startswith(('http://', 'https://')) else None)
            # --- ИНВАЛИДАЦИЯ КЭША ---
            cache_delete('news_list')
            cache_delete('news_page')
            invalidate_etag_cache('news_page')
            # --- КОНЕЦ ИНВАЛИДАЦИИ ---
        logger.info(f"[JSON API] Добавлен {category}: {title}")
        return jsonify(success=True, message="Видео успешно добавлено!")
    except Exception as e:
        logger.error(f"[JSON API] add_video error: {e}", exc_info=True)
        return jsonify(success=False, error=str(e)), 500

def add_video_command(update, context):
    user = update.message.from_user
    telegram_id = str(user.id)
    role = get_user_role(telegram_id)
    if role not in ['owner', 'admin']:
        update.message.reply_text("❌ You have no rights!")
        return
    text = update.message.text.strip()
    parts = text.split(' ', 2)
    if len(parts) < 3 or parts[1].lower() not in ['moment', 'trailer', 'news']:
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
    if telegram_id not in pending_video_data:
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
        # --- ИНВАЛИДАЦИЯ КЭША ---
        cache_delete('moments_list')
        cache_delete('moments_page')
        invalidate_etag_cache('moments_page')
        # --- КОНЕЦ ИНВАЛИДАЦИИ ---
    elif content_type == 'trailer':
        add_trailer(title, "Added via Telegram", video_url)
        # --- ИНВАЛИДАЦИЯ КЭША ---
        cache_delete('trailers_list')
        cache_delete('trailers_page')
        invalidate_etag_cache('trailers_page')
        # --- КОНЕЦ ИНВАЛИДАЦИИ ---
    elif content_type == 'news':
        add_news(title, "Added via Telegram", video_url)
        # --- ИНВАЛИДАЦИЯ КЭША ---
        cache_delete('news_list')
        cache_delete('news_page')
        invalidate_etag_cache('news_page')
        # --- КОНЕЦ ИНВАЛИДАЦИИ ---
    update.message.reply_text(f"✅ '{content_type}' '{title}' добавлено по ссылке!")
    cache_delete('moments_list')
    cache_delete('trailers_list')
    cache_delete('news_list')

def handle_pending_video_file(update, context):
    user = update.message.from_user
    telegram_id = str(user.id)
    logger.info(f"Получен видеофайл от пользователя {telegram_id}")
    if telegram_id not in pending_video_data:
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
    video_url, _ = get_cached_direct_video_url_advanced(file_id)
    if not video_url:
        error_msg = "❌ Не удалось получить прямую ссылку на видео из Telegram"
        logger.error(error_msg)
        update.message.reply_text(error_msg)
        return
    logger.info(f"Сгенерирована прямая ссылка: {video_url[:50]}...")
    try:
        if content_type == 'moment':
            add_moment(title, "Added via Telegram", video_url)
            # --- ИНВАЛИДАЦИЯ КЭША ---
            cache_delete('moments_list')
            cache_delete('moments_page')
            invalidate_etag_cache('moments_page')
            # --- КОНЕЦ ИНВАЛИДАЦИИ ---
        elif content_type == 'trailer':
            add_trailer(title, "Added via Telegram", video_url)
            # --- ИНВАЛИДАЦИЯ КЭША ---
            cache_delete('trailers_list')
            cache_delete('trailers_page')
            invalidate_etag_cache('trailers_page')
            # --- КОНЕЦ ИНВАЛИДАЦИИ ---
        elif content_type == 'news':
            add_news(title, "Added via Telegram", video_url)
            # --- ИНВАЛИДАЦИЯ КЭША ---
            cache_delete('news_list')
            cache_delete('news_page')
            invalidate_etag_cache('news_page')
            # --- КОНЕЦ ИНВАЛИДАЦИИ ---
        success_msg = f"✅ '{content_type}' '{title}' добавлено из файла!"
        logger.info(success_msg)
        update.message.reply_text(success_msg)
        cache_delete('moments_list')
        cache_delete('trailers_list')
        cache_delete('news_list')
    except Exception as e:
        error_msg = f"❌ Ошибка сохранения в БД: {e}"
        logger.error(error_msg, exc_info=True)
        update.message.reply_text(error_msg)

if dp:
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('menu', menu_command))
    dp.add_handler(CommandHandler('add_video', add_video_command))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_pending_video_text))
    dp.add_handler(MessageHandler(Filters.video & ~Filters.command, handle_pending_video_file))

# --- Start Bot ---
def start_bot():
    if updater:
        logger.info("Настройка Telegram бота для работы через Webhook...")
        logger.info("Установка Menu Button...")
        try:
            set_menu_button()
            logger.info("Menu Button успешно установлена.")
        except Exception as e:
            logger.error(f"Не удалось установить Menu Button при запуске: {e}")
        logger.info("Telegram бот готов принимать обновления через Webhook.")

# --- Health Check Endpoint ---
@app.route('/health')
def health_check():
    """Проверка состояния приложения"""
    try:
        redis_status = "OK" if redis_client else "Not configured"
        if redis_client:
            try:
                redis_client.ping()
            except Exception as e:
                redis_status = f"Connection error: {str(e)}"
        bot_status = "OK" if TOKEN else "Not configured"
        db_status = "Unknown"
        try:
            from database import get_db_connection
            conn = get_db_connection()
            conn.close()
            db_status = "OK"
        except Exception as e:
            db_status = f"Connection error: {str(e)}"
        return jsonify({
            'status': 'healthy',
            'services': {
                'redis': redis_status,
                'bot': bot_status,
                'database': db_status
            },
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Health check error: {e}")
        # ИСПРАВЛЕНО: синтаксическая ошибка
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

# --- Main ---
logger.info("Запуск Telegram бота...")
start_bot()
port = int(os.environ.get('PORT', 10000))
logger.info(f"Flask приложение будет запущено Gunicorn'ом на порту {port}...")
# --- Экспорт приложения для WSGI (например, Gunicorn) ---
# Gunicorn импортирует этот модуль и ожидает переменную с именем 'app'
# Объект app = Flask(...) уже создан выше в файле.
# Никакого дополнительного кода здесь не нужно, просто убедитесь, что 'app' существует.
# Убедись, что в railway.json указано startCommand: "gunicorn --bind 0.0.0.0:$PORT app:app"
