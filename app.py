# app.py - Полный исправленный код
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
import tempfile
import cv2
import numpy as np
from io import BytesIO

# --- Logging ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Config ---
TOKEN = os.environ.get('TELEGRAM_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://cinema-space-bot.onrender.com').strip().rstrip('/')
REDIS_URL = os.environ.get('REDIS_URL', None)
TMDB_API_KEY = os.environ.get('TMDB_API_KEY')

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

# --- Кэш для прямых ссылок ---
video_url_cache = {}

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
    except Exception as e:
        logger.error(f"Ошибка получения ссылки для file_id {file_id}: {e}")
        return None

def get_cached_direct_video_url(file_id, cache_time=3600):
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

# --- Функция для извлечения видео из поста Telegram ---
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
            logger.info("[ИЗВЛЕЧЕНИЕ] Сообщение успешно получено через forward_message")
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
    for row in data:
        item_id = row[0]
        reactions = get_reactions_count(item_type_plural, item_id) or {'like': 0, 'dislike': 0, 'star': 0, 'fire': 0}
        comments_count = len(get_comments(item_type_plural, item_id) or [])
        extra[item_id] = {'reactions': reactions, 'comments_count': comments_count}
    return extra

# --- Импорт функций базы данных ---
from database import (
    get_or_create_user, get_user_role,
    add_moment, add_trailer, add_news,
    get_all_moments, get_all_trailers, get_all_news,
    get_reactions_count, get_comments,
    add_reaction, add_comment,
    authenticate_admin, get_stats,
    delete_item, get_access_settings, update_access_settings,
    init_db, get_item_by_id, get_db_connection
)

# --- Routes ---
@app.route('/')
def index():
    """Главная страница основного приложения."""
    return render_template('index.html')

@app.route('/admin')
def admin_redirect():
    """Перенаправление в админ-панель."""
    if 'admin' in session:
        return redirect(url_for('admin_dashboard'))
    else:
        return redirect(url_for('admin_login'))

# --- НОВЫЙ МАРШРУТ ДЛЯ ПОИСКА ПО ССЫЛКЕ ---
@app.route('/search_by_link')
def search_by_link_page():
    """Отображает страницу поиска фильма по ссылке."""
    return render_template('search_by_link.html')

# --- Маршруты для вкладок ---
@app.route('/moments')
def moments():
    def generate_moments_html():
        try:
            data = get_all_moments() or []
            extra_map = build_extra_map(data, 'moments')
            combined_data = []
            for row in data:
                item_id = row[0]
                item_dict = {
                    'id': row[0],
                    'title': row[1] if len(row) > 1 else '',
                    'description': row[2] if len(row) > 2 else '',
                    'video_url': row[3] if len(row) > 3 else '',
                    'created_at': row[4] if len(row) > 4 else None
                }
                extra_info = extra_map.get(item_id, {'reactions': {'like': 0, 'dislike': 0, 'star': 0, 'fire': 0}, 'comments_count': 0})
                item_dict['reactions'] = extra_info.get('reactions', {'like': 0, 'dislike': 0, 'star': 0, 'fire': 0})
                item_dict['comments_count'] = extra_info.get('comments_count', 0)
                combined_data.append(item_dict)
            return render_template('moments.html', moments=combined_data)
        except Exception as e:
            return render_template('error.html', error=str(e))
    
    cached_html = get_cached_html('moments_page', generate_moments_html, expire=300)
    return cached_html

@app.route('/trailers')
def trailers():
    def generate_trailers_html():
        try:
            data = get_all_trailers() or []
            extra_map = build_extra_map(data, 'trailers')
            combined_data = []
            for row in data:
                item_id = row[0]
                item_dict = {
                    'id': row[0],
                    'title': row[1] if len(row) > 1 else '',
                    'description': row[2] if len(row) > 2 else '',
                    'video_url': row[3] if len(row) > 3 else '',
                    'created_at': row[4] if len(row) > 4 else None
                }
                extra_info = extra_map.get(item_id, {'reactions': {'like': 0, 'dislike': 0, 'star': 0, 'fire': 0}, 'comments_count': 0})
                item_dict['reactions'] = extra_info.get('reactions', {'like': 0, 'dislike': 0, 'star': 0, 'fire': 0})
                item_dict['comments_count'] = extra_info.get('comments_count', 0)
                combined_data.append(item_dict)
            return render_template('trailers.html', trailers=combined_data)
        except Exception as e:
            return render_template('error.html', error=str(e))
    
    cached_html = get_cached_html('trailers_page', generate_trailers_html, expire=300)
    return cached_html

@app.route('/news')
def news():
    def generate_news_html():
        try:
            data = get_all_news() or []
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
                item_dict['reactions'] = extra_info.get('reactions', {'like': 0, 'dislike': 0, 'star': 0, 'fire': 0})
                item_dict['comments_count'] = extra_info.get('comments_count', 0)
                combined_data.append(item_dict)
            return render_template('news.html', news=combined_data)
        except Exception as e:
            return render_template('error.html', error=str(e))
    
    cached_html = get_cached_html('news_page', generate_news_html, expire=300)
    return cached_html

# --- Детальные страницы ---
@app.route('/moments/<int:item_id>')
def moment_detail(item_id):
    """Отображает страницу одного момента."""
    item = get_item_by_id('moments', item_id)
    if not item:
        abort(404)
    reactions = get_reactions_count('moments', item_id)
    comments = get_comments('moments', item_id)
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
    item = get_item_by_id('trailers', item_id)
    if not item:
        abort(404)
    reactions = get_reactions_count('trailers', item_id)
    comments = get_comments('trailers', item_id)
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
    item = get_item_by_id('news', item_id)
    if not item:
        abort(404)
    reactions = get_reactions_count('news', item_id)
    comments = get_comments('news', item_id)
    item_dict = {
        'id': item[0],
        'title': item[1] if len(item) > 1 else '',
        'text': item[2] if len(item) > 2 else '',
        'image_url': item[3] if len(item) > 3 else '',
        'created_at': item[4] if len(item) > 4 else None
    }
    return render_template('news_detail.html', item=item_dict, reactions=reactions, comments=comments)

# --- API endpoints ---
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
            direct_url, error = extract_video_url_sync(video_url)
            if direct_url:
                video_url = direct_url
            else:
                return jsonify(success=False, error=error), 400
        
        if not video_url and 'video_file' in request.files:
            saved = save_uploaded_file(request.files['video_file'], ALLOWED_VIDEO_EXTENSIONS)
            if saved:
                video_url = saved
        
        if not video_url:
            return jsonify(success=False, error="Укажите ссылку на видео, пост Telegram или загрузите файл"), 400
        
        add_moment(title, desc, video_url)
        cache_delete('moments_list')
        cache_delete('moments_page')
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500

@app.route('/api/add_trailer', methods=['POST'])
def api_add_trailer():
    try:
        payload = _get_payload()
        title = payload.get('title', '').strip()
        desc = payload.get('description', '').strip()
        video_url = payload.get('video_url', '').strip()
        
        if video_url and ('t.me/' in video_url):
            direct_url, error = extract_video_url_sync(video_url)
            if direct_url:
                video_url = direct_url
            else:
                return jsonify(success=False, error=error), 400
        
        if not video_url and 'video_file' in request.files:
            saved = save_uploaded_file(request.files['video_file'], ALLOWED_VIDEO_EXTENSIONS)
            if saved:
                video_url = saved
        
        if not video_url:
            return jsonify(success=False, error="Укажите ссылку на видео, пост Telegram или загрузите файл"), 400
        
        add_trailer(title, desc, video_url)
        cache_delete('trailers_list')
        cache_delete('trailers_page')
        return jsonify(success=True)
    except Exception as e:
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
        cache_delete('news_page')
        return jsonify(success=True)
    except Exception as e:
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
        return jsonify(success=False, error=str(e)), 500

@app.route('/api/comments', methods=['GET'])
def api_get_comments():
    try:
        item_type = request.args.get('type')
        item_id = int(request.args.get('id'))
        comments = get_comments(item_type, item_id)
        return jsonify(comments=comments)
    except Exception as e:
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
        return jsonify(success=False, error=str(e)), 500

# --- Админ-панель ---
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

@app.route('/admin/dashboard')
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

@app.route('/admin/add_content')
@admin_required
def admin_add_content():
    """Форма добавления контента."""
    return render_template('admin/add_content.html')

@app.route('/admin/add_content', methods=['POST'])
@admin_required
def admin_add_content_post():
    """Обработка добавления контента."""
    try:
        content_type = request.form.get('content_type')
        title = request.form.get('title')
        description = request.form.get('description')
        telegram_url = request.form.get('telegram_url')
        video_file = request.files.get('video_file')

        if content_type == 'moment':
            if telegram_url:
                add_moment(title, description, telegram_url)
            elif video_file:
                saved_path = save_uploaded_file(video_file, ALLOWED_VIDEO_EXTENSIONS)
                if saved_path:
                    add_moment(title, description, saved_path)
        elif content_type == 'trailer':
            if telegram_url:
                add_trailer(title, description, telegram_url)
            elif video_file:
                saved_path = save_uploaded_file(video_file, ALLOWED_VIDEO_EXTENSIONS)
                if saved_path:
                    add_trailer(title, description, saved_path)
        elif content_type == 'news':
            add_news(title, description, telegram_url if telegram_url else None)

        return redirect(url_for('admin_content'))
    except Exception as e:
        return f"Ошибка: {str(e)}"

@app.route('/admin/delete/<content_type>/<int:content_id>')
@admin_required
def admin_delete(content_type, content_id):
    if content_type == 'moment':
        delete_item('moments', content_id)
        cache_delete('moments_list')
        cache_delete('moments_page')
    elif content_type == 'trailer':
        delete_item('trailers', content_id)
        cache_delete('trailers_list')
        cache_delete('trailers_page')
    elif content_type == 'news':
        delete_item('news', content_id)
        cache_delete('news_list')
        cache_delete('news_page')
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
            direct_url, error = extract_video_url_sync(post_link)
            if direct_url:
                video_url = direct_url
            else:
                return jsonify(success=False, error=error), 400
        
        if category == 'moment':
            add_moment(title, description, video_url)
            cache_delete('moments_list')
            cache_delete('moments_page')
        elif category == 'trailer':
            add_trailer(title, description, video_url)
            cache_delete('trailers_list')
            cache_delete('trailers_page')
        elif category == 'news':
            add_news(title, description, video_url if video_url.startswith(('http://', 'https://')) else None)
            cache_delete('news_list')
            cache_delete('news_page')
        
        return jsonify(success=True, message="Видео успешно добавлено!")
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500

# --- Telegram Bot Handlers ---
if TOKEN:
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    def start(update, context):
        """Обработчик команды /start"""
        try:
            user = update.message.from_user
            telegram_id = str(user.id)
            get_or_create_user(
                telegram_id=telegram_id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
            
            app_url = f"{WEBHOOK_URL}/?mode=fullscreen"
            keyboard = [[
                InlineKeyboardButton(
                    "🌌 КиноВселенная",
                    web_app=WebAppInfo(url=app_url)
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
        except Exception as e:
            logger.error(f"Ошибка в обработчике /start: {e}")

    def menu_command(update, context):
        """Команда для установки/переустановки Menu Button"""
        try:
            success = set_menu_button()
            if success:
                update.message.reply_text("✅ Кнопка меню успешно установлена/обновлена!")
            else:
                update.message.reply_text("❌ Ошибка установки кнопки меню")
        except Exception as e:
            update.message.reply_text("❌ Ошибка при установке кнопки меню")

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
        
        if telegram_id not in pending_video_data:
            return
        
        data = pending_video_data.pop(telegram_id)
        content_type, title = data['content_type'], data['title']
        
        if not update.message.video:
            update.message.reply_text("❌ Это не видео. Пришли файл видео или ссылку.")
            pending_video_data[telegram_id] = data
            return
        
        file_id = update.message.video.file_id
        video_url = get_cached_direct_video_url(file_id)
        
        if not video_url:
            update.message.reply_text("❌ Не удалось получить прямую ссылку на видео из Telegram")
            return
        
        try:
            if content_type == 'moment':
                add_moment(title, "Added via Telegram", video_url)
            elif content_type == 'trailer':
                add_trailer(title, "Added via Telegram", video_url)
            elif content_type == 'news':
                add_news(title, "Added via Telegram", video_url)
            
            update.message.reply_text(f"✅ '{content_type}' '{title}' добавлено из файла!")
            cache_delete('moments_list')
            cache_delete('trailers_list')
            cache_delete('news_list')
        except Exception as e:
            update.message.reply_text(f"❌ Ошибка сохранения в БД: {e}")

    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('menu', menu_command))
    dp.add_handler(CommandHandler('add_video', add_video_command))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_pending_video_text))
    dp.add_handler(MessageHandler(Filters.video & ~Filters.command, handle_pending_video_file))

# --- Health Check ---
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
            conn = get_db_connection()
            conn.close()
            db_status = "OK"
        except Exception as e:
            db_status = f"Connection error: {str(e)}"
        
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
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

# --- Main ---
if __name__ == '__main__':
    try:
        init_db()
        logger.info("База данных инициализирована.")
    except Exception as e:
        logger.error(f"DB init error: {e}")
    
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"Запуск Flask приложения на порту {port}...")
    app.run(host='0.0.0.0', port=port)
