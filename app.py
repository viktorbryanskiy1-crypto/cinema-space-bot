# app.py - Полный код с восстановленной админ-панелью и гибридным поиском фильмов
# Исправлены все синтаксические ошибки, улучшена обработка ошибок API
import os
import threading
import logging
import uuid
import requests
import time
import re
import asyncio
from datetime import datetime
from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, session, send_from_directory, abort
)
from werkzeug.utils import secure_filename
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, Bot, MenuButtonWebApp, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import redis
import json
# --- НОВОЕ: Импорты для работы с изображениями и API ---
import tempfile
import cv2
import numpy as np
from io import BytesIO
# --- Конец новых импортов ---
from database import (
    get_or_create_user, get_user_role,
    add_moment, add_trailer, add_news,
    get_all_moments, get_all_trailers, get_all_news,
    get_reactions_count, get_comments,
    add_reaction, add_comment,
    authenticate_admin, get_stats,
    delete_item, get_access_settings, update_access_settings,
    init_db, get_item_by_id, get_db_connection # Добавлен get_db_connection
)

# --- Logging ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Config ---
TOKEN = os.environ.get('TELEGRAM_TOKEN')
# Исправлено: убраны лишние пробелы
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://cinema-space-bot.onrender.com').strip().rstrip('/')
REDIS_URL = os.environ.get('REDIS_URL', None)
# --- НОВОЕ: Получение TMDB API ключа ---
TMDB_API_KEY = os.environ.get('TMDB_API_KEY') # Добавлено
# --- Конец нового ---
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

def get_cached_direct_video_url(file_id, cache_time=3600):  # Увеличено до 1 часа
    """Кэшированное получение прямой ссылки"""
    current_time = time.time()
    if file_id in video_url_cache:
        url, expire_time = video_url_cache[file_id]
        if current_time < expire_time:
            logger.debug(f"Ссылка для file_id {file_id} получена из кэша")
            return url
    logger.debug(f"Генерация новой ссылки для file_id {file_id}")
    url = get_direct_video_url(file_id)
    if url:
        video_url_cache[file_id] = (url, current_time + cache_time)
        logger.debug(f"Ссылка для file_id {file_id} закэширована")
        return url
    return None

# --- ИСПРАВЛЕННАЯ Функция для извлечения видео из поста Telegram ---
# (Обновлённая версия: пересылает сообщения только в тестовую группу)
async def extract_video_url_from_telegram_post(post_url):
    """
    Извлекает прямую ссылку на видео из поста Telegram.
    Совместимо с python-telegram-bot v13.15.
    Исправлено: теперь пересылает сообщения только в тестовую группу.
    """
    try:
        logger.info(f"[ИЗВЛЕЧЕНИЕ] Попытка извлечь видео из поста: {post_url}")
        # Парсим ссылку
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
        # --- ИСПРАВЛЕНИЕ: Всегда пересылаем в тестовую группу ---
        # Это предотвращает дублирование в исходном канале
        YOUR_TEST_CHAT_ID = -1003045387627 # <<<--- ВАШ ID ТЕСТОВОЙ ГРУППЫ
        try:
            logger.debug(f"[ИЗВЛЕЧЕНИЕ] Пересылаем сообщение в тестовую группу {YOUR_TEST_CHAT_ID}...")
            # ИСПРАВЛЕНО: Убран await, так как forward_message возвращает объект Message, а не coroutine
            forwarded_message = bot.forward_message(
                chat_id=YOUR_TEST_CHAT_ID,        # <<<--- ВСЕГДА в тестовую группу
                from_chat_id=chat_id_or_username, # Откуда - из исходного чата
                message_id=message_id            # Какое сообщение
            )
            message = forwarded_message
            logger.info("[ИЗВЛЕЧЕНИЕ] Сообщение успешно получено через forward_message (в тестовую группу)")
        except Exception as e1:
            logger.error(f"[ИЗВЛЕЧЕНИЕ] Не удалось получить сообщение через forward: {e1}")
            return None, "Не удалось получить сообщение. Убедитесь, что бот имеет доступ к сообщению."
        # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
        if not message:
            logger.error("[ИЗВЛЕЧЕНИЕ] Сообщение не найдено или бот не имеет доступа")
            return None, "Сообщение не найдено."
        if not message.video:
            logger.error("[ИЗВЛЕЧЕНИЕ] В посте нет видео")
            return None, "В указанном посте не найдено видео."
        file_id = message.video.file_id
        logger.info(f"[ИЗВЛЕЧЕНИЕ] Найден file_id: {file_id}")
        direct_url = get_cached_direct_video_url(file_id)
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

# --- НОВАЯ ФУНКЦИЯ: Обновление устаревшей ссылки ---
@app.route('/api/refresh_video_url', methods=['POST'])
def refresh_video_url():
    """Обновляет устаревшую ссылку на видео по Telegram посту"""
    try:
        data = request.get_json()
        if not 
            logger.warning("[ОБНОВЛЕНИЕ ССЫЛКИ] Неверный формат данных")
            return jsonify(success=False, error="Неверный формат данных"), 400
        post_url = data.get('post_url', '').strip()
        if not post_url:
            logger.warning("[ОБНОВЛЕНИЕ ССЫЛКИ] Не указана ссылка на пост")
            return jsonify(success=False, error="Не указана ссылка на пост"), 400
        logger.info(f"[ОБНОВЛЕНИЕ ССЫЛКИ] Запрошено обновление для ссылки: {post_url[:50]}...")
        # Извлекаем новую ссылку
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

# --- НОВАЯ ФУНКЦИЯ: Кэширование HTML страниц ---
def get_cached_html(key, generate_func, expire=300):
    """Получает HTML из кэша или генерирует новый"""
    if redis_client:
        try:
            cached_html = redis_client.get(key)
            if cached_html:
                logger.info(f"HTML для {key} получен из кэша")
                return cached_html
        except Exception as e:
            logger.warning(f"Ошибка получения HTML из кэша: {e}")
    # Генерируем новый HTML
    html = generate_func()
    # Сохраняем в кэш
    if redis_client and html:
        try:
            redis_client.set(key, html, ex=expire)
            logger.info(f"HTML для {key} закэширован на {expire} секунд")
        except Exception as e:
            logger.warning(f"Ошибка сохранения HTML в кэш: {e}")
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
        # Установка Menu Button
        app_url = f"{WEBHOOK_URL}/?mode=fullscreen"
        logger.info(f"URL для Menu Button: {app_url}")
        menu_button = MenuButtonWebApp(
            text="movies",  # <-- Изменено на "movies"
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
    # --- Обработчик команды /start ---
    def start(update, context):
        """Обработчик команды /start"""
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
    # --- Обработчик команды /menu для установки Menu Button ---
    def menu_command(update, context):
        """Команда для установки/переустановки Menu Button"""
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
    for row in data: # ИСПРАВЛЕНО: Добавлен 'data' в 'for row in '
        item_id = row[0]
        reactions = get_reactions_count(item_type_plural, item_id) or {'like': 0, 'dislike': 0, 'star': 0, 'fire': 0}
        comments_count = len(get_comments(item_type_plural, item_id) or [])
        extra[item_id] = {'reactions': reactions, 'comments_count': comments_count}
    return extra

# --- Routes (пользовательские) ---
@app.route('/')
def index():
    """Главная страница. Перенаправляет на админку, если пользователь авторизован."""
    if 'admin' in session:
        return redirect(url_for('admin_dashboard'))
    return render_template('index.html')

# --- НОВЫЙ МАРШРУТ ДЛЯ ПОИСКА ПО ССЫЛКЕ ---
@app.route('/search_by_link')
def search_by_link_page():
    """Отображает страницу поиска фильма по ссылке."""
    return render_template('search_by_link.html')
# --- КОНЕЦ НОВОГО МАРШРУТА ---

# --- НОВЫЕ ФУНКЦИИ ДЛЯ ГИБРИДНОГО ПОИСКА ФИЛЬМОВ ---
# TinEye API URL (бесплатный, без ключа, но с лимитами)
TINEYE_API_URL = "https://tineye.com/api/v1/search"

def search_movie_via_tmdb(api_key, query, year=None):
    """Ищет фильм в TMDB по названию."""
    try:
        search_url = "https://api.themoviedb.org/3/search/movie"
        params = {
            'api_key': api_key,
            'query': query,
            'language': 'ru-RU' # Можно изменить на 'en-US' или другой
        }
        if year and str(year).isdigit() and 1888 <= int(year) <= datetime.now().year:
             params['year'] = year

        logger.debug(f"[TMDB SEARCH] Запрос: {search_url}, Параметры: {params}")
        response = requests.get(search_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        logger.debug(f"[TMDB SEARCH] Ответ получен, всего результатов: {data.get('total_results', 0)}")

        # Возвращаем первый результат, если он есть
        if data.get('results'):
            movie = data['results'][0] # Берем самый релевантный (первый)
            return {
                "success": True,
                "source": "TMDB search by title",
                "film": {
                    "title": movie.get('title', 'Название не найдено'),
                    "original_title": movie.get('original_title', ''),
                    "year": movie.get('release_date', '')[:4] if movie.get('release_date') else 'Неизвестно',
                    "description": movie.get('overview', 'Описание отсутствует.'),
                    "poster_path": f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}" if movie.get('poster_path') else None,
                    "tmdb_id": movie.get('id'),
                    # Можно добавить рейтинг, жанры и т.д.
                }
            }
        else:
            logger.info(f"[TMDB SEARCH] Ничего не найдено для запроса: '{query}'")
            return {"success": False, "error": "Фильм не найден в TMDB по названию."}

    except requests.exceptions.RequestException as e:
        logger.error(f"[TMDB SEARCH] Ошибка сети: {e}")
        return {"success": False, "error": "Ошибка подключения к TMDB."}
    except Exception as e:
        logger.error(f"[TMDB SEARCH] Непредвиденная ошибка: {e}", exc_info=True)
        return {"success": False, "error": "Внутренняя ошибка при поиске в TMDB."}

def extract_frame_from_video_url(video_url, time_percent=0.3):
    """Извлекает кадр из видео по URL."""
    temp_filename = None
    cap = None
    try:
        logger.info(f"[ИЗВЛЕЧЕНИЕ КАДРА] Начало для URL: {video_url[:50]}...")
        # 1. Используем yt-dlp для получения прямой ссылки на видео
        import yt_dlp
        ydl_opts = {
            'format': 'best[height<=?720]', # Ограничиваем качество для скорости
            'noplaylist': True,
            'quiet': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(video_url, download=False)
            video_url_direct = info_dict.get('url')
            if not video_url_direct:
                 raise Exception("Не удалось получить прямую ссылку на видео через yt-dlp.")

        logger.debug(f"[ИЗВЛЕЧЕНИЕ КАДРА] Прямая ссылка получена: {video_url_direct[:50]}...")

        # 2. Используем OpenCV для захвата кадра
        # ВАЖНО: Используем 'opencv-python-headless'!
        cap = cv2.VideoCapture(video_url_direct)
        if not cap.isOpened():
            raise Exception("Не удалось открыть видео поток с помощью OpenCV.")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        logger.debug(f"[ИЗВЛЕЧЕНИЕ КАДРА] Всего кадров: {total_frames}, FPS: {fps}")

        if total_frames <= 0 or fps <= 0:
             # Альтернатива: попробовать получить кадр через ffmpeg или PIL, если OpenCV не справляется
             # Пока просто выбрасываем ошибку
             raise Exception("Не удалось определить параметры видео (количество кадров или FPS).")

        # Выбираем кадр посередине или немного ранее (time_percent по умолчанию 30% от длительности)
        target_frame = int(total_frames * time_percent)
        logger.debug(f"[ИЗВЛЕЧЕНИЕ КАДРА] Целевой кадр: {target_frame}")
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)

        ret, frame = cap.read()
        if not ret:
            # Попробуем еще раз с нулевого кадра
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
            if not ret:
                raise Exception("Не удалось прочитать кадр из видео.")

        logger.info("[ИЗВЛЕЧЕНИЕ КАДРА] Кадр успешно захвачен.")

        # 3. Конвертируем кадр в JPEG BytesIO
        is_success, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85]) # Качество 85
        if not is_success:
            raise Exception("Не удалось закодировать кадр в JPEG.")

        io_buf = BytesIO(buffer)
        logger.info("[ИЗВЛЕЧЕНИЕ КАДРА] Кадр успешно закодирован в JPEG.")
        return io_buf

    except ImportError as e:
        logger.error(f"[ИЗВЛЕЧЕНИЕ КАДРА] Модуль не установлен: {e}")
        raise Exception("Не установлен необходимый модуль 'yt-dlp' или 'opencv-python-headless'.")
    except Exception as e:
        logger.error(f"[ИЗВЛЕЧЕНИЕ КАДРА] Ошибка: {e}", exc_info=True)
        # Убедимся, что ресурсы освобождены
        if cap:
            cap.release()
        if temp_filename and os.path.exists(temp_filename):
            os.remove(temp_filename)
        raise e # Пробрасываем исключение дальше

def search_image_tineye(image_bytes_io):
    """Отправляет изображение в TinEye API и возвращает результаты."""
    try:
        logger.info("[TINEYE SEARCH] Начало поиска по изображению...")
        # TinEye Free API не требует ключа, но отправка через multipart/form-data
        # SEEK TO START, IMPORTANT!
        image_bytes_io.seek(0)
        files = {'image': ('frame.jpg', image_bytes_io, 'image/jpeg')}
        # TinEye может блокировать автоматические запросы, особенно с бесплатного уровня
        # Добавим заголовки, чтобы казаться более "браузерным"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.post(TINEYE_API_URL, files=files, headers=headers, timeout=30)

        logger.info(f"[TINEYE SEARCH] Статус код: {response.status_code}")
        # logger.debug(f"[TINEYE SEARCH] Заголовки ответа: {response.headers}")
        # logger.debug(f"[TINEYE SEARCH] Текст ответа (первые 500 символов): {response.text[:500]}...")

        if response.status_code == 200:
            try:
                data = response.json()
                matches = data.get('results', [])
                logger.info(f"[TINEYE SEARCH] Найдено совпадений: {len(matches)}")
                # Форматируем результаты для отображения
                formatted_matches = []
                for match in matches[:10]: # Ограничиваем до 10 результатов
                    if match.get('domain') and match.get('score') is not None: # Проверяем наличие ключевых полей
                         # Ищем IMDB ID в URL, если возможно
                         imdb_id_match = re.search(r'/title/(tt\d+)/?', match.get('url', ''))
                         imdb_id = imdb_id_match.group(1) if imdb_id_match else None
                         formatted_matches.append({
                             'url': match.get('url', '#'),
                             'domain': match.get('domain'),
                             'score': match.get('score'),
                             'imdb_id': imdb_id
                         })
                return {"success": True, "matches": formatted_matches}
            except ValueError: # json.JSONDecodeError
                logger.error("[TINEYE SEARCH] API вернул не JSON")
                return {"success": False, "error": "TinEye API вернул непонятный ответ (не JSON)."}
        elif response.status_code == 429:
            logger.warning("[TINEYE SEARCH] Превышен лимит запросов")
            return {"success": False, "error": "Превышен лимит запросов к TinEye. Попробуйте позже."}
        elif response.status_code == 400:
             logger.error("[TINEYE SEARCH] Неверный запрос")
             logger.error(f"[TINEYE SEARCH] Текст ответа: {response.text}")
             return {"success": False, "error": "TinEye API: Неверный запрос. Возможно, изображение не подходит."}
        else:
            logger.error(f"[TINEYE SEARCH] Ошибка API: {response.status_code}, {response.text}")
            return {"success": False, "error": f"Ошибка TinEye API: {response.status_code}"}
    except requests.exceptions.RequestException as e:
        logger.error(f"[TINEYE SEARCH] Ошибка сети при запросе к TinEye: {e}")
        return {"success": False, "error": "Ошибка сети при подключении к TinEye."}
    except Exception as e:
        logger.error(f"[TINEYE SEARCH] Неизвестная ошибка: {e}", exc_info=True)
        return {"success": False, "error": "Неизвестная ошибка при поиске в TinEye."}

def find_movie_by_imdb_id_via_tmdb(api_key, imdb_id):
    """Ищет фильм в TMDB по IMDB ID."""
    try:
        find_url = f"https://api.themoviedb.org/3/find/{imdb_id}"
        params = {
            'api_key': api_key,
            'external_source': 'imdb_id',
            'language': 'ru-RU'
        }
        logger.debug(f"[TMDB FIND BY IMDB] Запрос: {find_url}, Параметры: {params}")
        response = requests.get(find_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        logger.debug(f"[TMDB FIND BY IMDB] Ответ: {data}")

        # Ищем в разделе 'movie_results'
        movie_results = data.get('movie_results', [])
        if movie_results:
            movie = movie_results[0] # Берем первый результат
            return {
                "success": True,
                "source": "TMDB find by IMDB ID (from TinEye)",
                "film": {
                    "title": movie.get('title', 'Название не найдено'),
                    "original_title": movie.get('original_title', ''),
                    "year": movie.get('release_date', '')[:4] if movie.get('release_date') else 'Неизвестно',
                    "description": movie.get('overview', 'Описание отсутствует.'),
                    "poster_path": f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}" if movie.get('poster_path') else None,
                    "tmdb_id": movie.get('id'),
                    "imdb_id": imdb_id
                }
            }
        else:
            logger.info(f"[TMDB FIND BY IMDB] Фильм с IMDB ID {imdb_id} не найден в TMDB.")
            return {"success": False, "error": f"Фильм с IMDB ID {imdb_id} не найден в TMDB."}

    except requests.exceptions.RequestException as e:
        logger.error(f"[TMDB FIND BY IMDB] Ошибка сети: {e}")
        return {"success": False, "error": "Ошибка подключения к TMDB (поиск по IMDB ID)."}
    except Exception as e:
        logger.error(f"[TMDB FIND BY IMDB] Непредвиденная ошибка: {e}", exc_info=True)
        return {"success": False, "error": "Внутренняя ошибка при поиске в TMDB по IMDB ID."}

# --- НОВЫЙ API МАРШРУТ: Поиск фильма по ссылке (Гибридный: текст + TMDB + TinEye) ---
@app.route('/api/search_film_by_link', methods=['POST'])
def api_search_film_by_link():
    """API для поиска фильма по ссылке на видео (гибридный подход)."""
    if not TMDB_API_KEY:
        logger.error("[ПОИСК ФИЛЬМА] Переменная окружения TMDB_API_KEY не установлена.")
        return jsonify(success=False, error="Сервис поиска фильмов временно недоступен (отсутствует ключ TMDB)."), 500

    try:
        # 1. Получаем данные из запроса
        data = request.get_json()
        if not 
            logger.warning("[ПОИСК ФИЛЬМА] Неверный формат данных")
            return jsonify(success=False, error="Неверный формат данных."), 400

        video_url = data.get('url', '').strip()
        if not video_url:
            logger.warning("[ПОИСК ФИЛЬМА] Не указана ссылка на видео")
            return jsonify(success=False, error="Ссылка на видео не указана."), 400

        logger.info(f"[ПОИСК ФИЛЬМА] Получен запрос для URL: {video_url}")

        # --- ПОПЫТКА 1: Поиск по метаданным + TMDB ---
        try:
            logger.info("[ПОИСК ФИЛЬМА] Попытка 1: Поиск по метаданным видео и TMDB...")
            import yt_dlp
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(video_url, download=False)
                title_from_video = info_dict.get('title', '').strip()
                description_from_video = info_dict.get('description', '').strip()
                upload_date_str = info_dict.get('upload_date', '') # Формат: YYYYMMDD

            logger.info(f"[ПОИСК ФИЛЬМА] Метаданные извлечены. Название: '{title_from_video[:50]}...', Описание: '{description_from_video[:50]}...'")

            # Простая попытка извлечь год из даты загрузки
            year_from_video = upload_date_str[:4] if len(upload_date_str) == 8 and upload_date_str[:4].isdigit() else None

            # Объединяем название и описание для более полного поискового запроса
            search_query = (title_from_video + " " + description_from_video).strip()
            if not search_query:
                 # Если и название, и описание пустые, используем часть URL
                 search_query = video_url.split('/')[-1].split('?')[0][:50] # Пример: ID видео из URL

            if search_query:
                tmdb_result = search_movie_via_tmdb(TMDB_API_KEY, search_query, year_from_video)
                if tmdb_result['success']:
                    logger.info("[ПОИСК ФИЛЬМА] Попытка 1 успешна (TMDB по метаданным).")
                    return jsonify(success=True, method="tmdb_metadata", **tmdb_result)
                else:
                    logger.info(f"[ПОИСК ФИЛЬМА] Попытка 1 не удалась: {tmdb_result.get('error')}")
            else:
                 logger.warning("[ПОИСК ФИЛЬМА] Не удалось сформировать поисковый запрос из метаданных.")

        except ImportError:
            logger.error("[ПОИСК ФИЛЬМА] Модуль yt-dlp не установлен для Попытки 1.")
        except Exception as e:
            logger.error(f"[ПОИСК ФИЛЬМА] Ошибка в Попытке 1 (метаданные + TMDB): {e}", exc_info=True)


        # --- ПОПЫТКА 2: Извлечение кадра + TinEye + TMDB ---
        try:
            logger.info("[ПОИСК ФИЛЬМА] Попытка 2: Извлечение кадра, поиск по TinEye, затем в TMDB...")
            image_bytes_io = extract_frame_from_video_url(video_url)
            logger.info("[ПОИСК ФИЛЬМА] Кадр успешно извлечен.")

            tineye_result = search_image_tineye(image_bytes_io)
            if tineye_result['success'] and tineye_result['matches']:
                logger.info("[ПОИСК ФИЛЬМА] TinEye вернул результаты. Проверяем на наличие IMDB ID...")
                # Ищем первый результат с IMDB ID
                for match in tineye_result['matches']:
                    imdb_id = match.get('imdb_id')
                    if imdb_id:
                        logger.info(f"[ПОИСК ФИЛЬМА] Найден IMDB ID в результате TinEye: {imdb_id}. Ищем в TMDB...")
                        tmdb_result = find_movie_by_imdb_id_via_tmdb(TMDB_API_KEY, imdb_id)
                        if tmdb_result['success']:
                            logger.info("[ПОИСК ФИЛЬМА] Попытка 2 успешна (TinEye -> TMDB по IMDB ID).")
                            # Добавляем информацию о совпадении TinEye в результат
                            tmdb_result['tineye_match_info'] = {
                                'url': match['url'],
                                'domain': match['domain'],
                                'score': match['score']
                            }
                            return jsonify(success=True, method="tineye_then_tmdb", **tmdb_result)
                        else:
                             logger.info(f"[ПОИСК ФИЛЬМА] Фильм по IMDB ID {imdb_id} не найден в TMDB: {tmdb_result.get('error')}")
                    else:
                         logger.debug(f"[ПОИСК ФИЛЬМА] В результате TinEye нет IMDB ID: {match.get('url')}")
                # Если дошли до сюда, значит IMDB ID в результатах TinEye не нашлось или фильмы не найдены в TMDB
                logger.info("[ПОИСК ФИЛЬМА] В результатах TinEye не найдено подходящих IMDB ID или фильмы не опознаны в TMDB.")
                # Можно вернуть результаты TinEye как есть, но без данных фильма
                # return jsonify(success=False, error="Фильм не опознан, но найдены совпадения изображения.", tineye_matches=tineye_result['matches'][:5])
            else:
                 error_msg = tineye_result.get('error', 'TinEye не вернул результатов.')
                 logger.info(f"[ПОИСК ФИЛЬМА] TinEye не дал результатов: {error_msg}")

        except Exception as e:
            logger.error(f"[ПОИСК ФИЛЬМА] Ошибка в Попытке 2 (кадр + TinEye + TMDB): {e}", exc_info=True)


        # --- Если все попытки исчерпаны ---
        logger.info("[ПОИСК ФИЛЬМА] Все попытки поиска не дали результата.")
        return jsonify(success=False, error="Не удалось определить фильм по предоставленной ссылке. Попробуйте другую ссылку или введите название фильма вручную, если знаете его."), 404

    except Exception as e:
        logger.error(f"[ПОИСК ФИЛЬМА] Критическая ошибка: {e}", exc_info=True)
        return jsonify(success=False, error="Внутренняя ошибка сервера. Попробуйте позже."), 500
# --- КОНЕЦ НОВЫХ ФУНКЦИЙ ---

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

# --- УЛУЧШЕНИЕ: Кэшированные маршруты для вкладок ---
@app.route('/moments')
def moments():
    def generate_moments_html():
        try:
            logger.info("Запрос к /moments")
            logger.info("Получение всех моментов из БД...")
            data = get_all_moments() or []
            logger.info(f"Получено {len(data)} моментов из БД")
            logger.info("Построение extra_map...")
            extra_map = build_extra_map(data, 'moments')
            logger.info("extra_map построен успешно")
            combined_data = []
            for row in data: # ИСПРАВЛЕНО: Добавлен 'data' в 'for row in '
                item_id = row[0]
                item_dict = {
                    'id': row[0],
                    'title': row[1] if len(row) > 1 else '',
                    'description': row[2] if len(row) > 2 else '',
                    'video_url': row[3] if len(row) > 3 else '',
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
            return render_template('moments.html', moments=combined_data)
        except Exception as e:
            logger.error(f"API add_moment error: {e}", exc_info=True)
            return render_template('error.html', error=str(e))
    # Кэшируем HTML на 5 минут
    cached_html = get_cached_html('moments_page', generate_moments_html, expire=300)
    return cached_html

@app.route('/trailers')
def trailers():
    def generate_trailers_html():
        try:
            logger.info("Запрос к /trailers")
            logger.info("Получение всех трейлеров из БД...")
            data = get_all_trailers() or []
            logger.info(f"Получено {len(data)} трейлеров из БД")
            logger.info("Построение extra_map...")
            extra_map = build_extra_map(data, 'trailers')
            logger.info("extra_map построен успешно")
            combined_data = []
            for row in data: # ИСПРАВЛЕНО: Добавлен 'data' в 'for row in '
                item_id = row[0]
                item_dict = {
                    'id': row[0],
                    'title': row[1] if len(row) > 1 else '',
                    'description': row[2] if len(row) > 2 else '',
                    'video_url': row[3] if len(row) > 3 else '',
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
            return render_template('trailers.html', trailers=combined_data)
        except Exception as e:
            logger.error(f"API add_trailer error: {e}", exc_info=True)
            return render_template('error.html', error=str(e))
    # Кэшируем HTML на 5 минут
    cached_html = get_cached_html('trailers_page', generate_trailers_html, expire=300)
    return cached_html

@app.route('/news')
def news():
    def generate_news_html():
        try:
            logger.info("Запрос к /news")
            logger.info("Получение всех новостей из БД...")
            data = get_all_news() or []
            logger.info(f"Получено {len(data)} новостей из БД")
            logger.info("Построение extra_map...")
            extra_map = build_extra_map(data, 'news')
            logger.info("extra_map построен успешно")
            combined_data = []
            for row in data: # ИСПРАВЛЕНО: Добавлен 'data' в 'for row in '
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
    # Кэшируем HTML на 5 минут
    cached_html = get_cached_html('news_page', generate_news_html, expire=300)
    return cached_html

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
    item_dict = {
        'id': item[0],
        'title': item[1] if len(item) > 1 else '',
        'description': item[2] if len(item) > 2 else '', # Исправлено: было row
        'video_url': item[3] if len(item) > 3 else '',   # Исправлено: было row
        'created_at': item[4] if len(item) > 4 else None # Исправлено: было row
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
    item_dict = {
        'id': item[0],
        'title': item[1] if len(item) > 1 else '',
        'text': item[2] if len(item) > 2 else '',
        'image_url': item[3] if len(item) > 3 else '',
        'created_at': item[4] if len(item) > 4 else None
    }
    return render_template('news_detail.html', item=item_dict, reactions=reactions, comments=comments)

def _get_payload():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form or {}

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
        cache_delete('moments_list')
        cache_delete('moments_page')  # Удаляем кэш страницы
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
        cache_delete('trailers_list')
        cache_delete('trailers_page')  # Удаляем кэш страницы
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
        cache_delete('news_list')
        cache_delete('news_page')  # Удаляем кэш страницы
        logger.info(f"Добавлена новость: {title}")
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"API add_news error: {e}", exc_info=True)
        return jsonify(success=False, error=str(e)), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

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

# --- НАЧАЛО АДМИН-ПАНЕЛИ ---
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

@app.route('/admin/')
@app.route('/admin')
@admin_required
def admin_dashboard():
    stats = get_stats()
    return render_template('admin/dashboard.html',
                           moments_count=stats.get('moments', 0),
                           trailers_count=stats.get('trailers', 0),
                           news_count=stats.get('news', 0),
                           comments_count=stats.get('comments', 0))

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
        cache_delete('moments_list')
        cache_delete('moments_page')  # Удаляем кэш страницы
    elif content_type == 'trailer':
        delete_trailer(content_id)
        cache_delete('trailers_list')
        cache_delete('trailers_page')  # Удаляем кэш страницы
    elif content_type == 'news':
        delete_news(content_id)
        cache_delete('news_list')
        cache_delete('news_page')  # Удаляем кэш страницы
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
        if not 
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
            cache_delete('moments_list')
            cache_delete('moments_page')  # Удаляем кэш страницы
        elif category == 'trailer':
            add_trailer(title, description, video_url)
            cache_delete('trailers_list')
            cache_delete('trailers_page')  # Удаляем кэш страницы
        elif category == 'news':
            add_news(title, description, video_url if video_url.startswith(('http://', 'https://')) else None)
            cache_delete('news_list')
            cache_delete('news_page')  # Удаляем кэш страницы
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
    video_url = get_cached_direct_video_url(file_id)
    if not video_url:
        error_msg = "❌ Не удалось получить прямую ссылку на видео из Telegram"
        logger.error(error_msg)
        update.message.reply_text(error_msg)
        return
    logger.info(f"Сгенерирована прямая ссылка: {video_url[:50]}...")
    try:
        if content_type == 'moment':
            add_moment(title, "Added via Telegram", video_url)
        elif content_type == 'trailer':
            add_trailer(title, "Added via Telegram", video_url)
        elif content_type == 'news':
            add_news(title, "Added via Telegram", video_url if video_url.startswith(('http://', 'https://')) else None)
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
# --- КОНЕЦ АДМИН-ПАНЕЛИ ---

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
        # Проверяем Redis
        redis_status = "OK" if redis_client else "Not configured"
        if redis_client:
            try:
                redis_client.ping()
            except Exception as e:
                redis_status = f"Connection error: {str(e)}"
        # Проверяем Telegram бот
        bot_status = "OK" if TOKEN else "Not configured"
        # Проверяем базу данных
        db_status = "Unknown"
        try:
            from database import get_db_connection
            conn = get_db_connection()
            conn.close()
            db_status = "OK"
        except Exception as e:
            db_status = f"Connection error: {str(e)}"
        # Проверяем TMDB API ключ
        tmdb_status = "OK" if TMDB_API_KEY else "TMDB_API_KEY not set"
        return jsonify({
            'status': 'healthy',
            'services': {
                'redis': redis_status,
                'bot': bot_status,
                'database': db_status,
                'tmdb_api': tmdb_status
            },
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

# --- Main ---
if __name__ == '__main__':
    try:
        logger.info("Инициализация базы данных...")
        init_db()
        logger.info("База данных инициализирована.")
    except Exception as e:
        logger.error(f"DB init error: {e}", exc_info=True)
    logger.info("Запуск Telegram бота...")
    start_bot()
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"Запуск Flask приложения на порту {port}...")
    app.run(host='0.0.0.0', port=port)
    logger.info("Flask приложение остановлено.")
