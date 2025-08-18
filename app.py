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
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, Bot
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
        redis_client = None
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

# --- Кэш для прямых ссылок на видео ---
video_url_cache = {}


def get_direct_video_url(file_id):
    """Генерирует прямую ссылку на видео из file_id через Telegram API."""
    bot_token = TOKEN
    if not bot_token:
        logger.error("TELEGRAM_TOKEN не установлен")
        return None

    try:
        file_info_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
        response = requests.get(file_info_url, timeout=10)
        response.raise_for_status()
        json_response = response.json()

        if not json_response.get('ok'):
            logger.error(f"Ошибка Telegram API: {json_response}")
            return None

        file_path = json_response['result']['file_path']
        direct_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        logger.info(f"Сгенерирована прямая ссылка: {direct_url}")
        return direct_url
    except Exception as e:
        logger.error(f"Ошибка при получении ссылки для file_id {file_id}: {e}")
        return None


def get_cached_direct_video_url(file_id, cache_time=3600):
    """Кэширует прямую ссылку на видео."""
    current_time = time.time()
    if file_id in video_url_cache:
        url, expire_time = video_url_cache[file_id]
        if current_time < expire_time:
            return url

    url = get_direct_video_url(file_id)
    if url:
        video_url_cache[file_id] = (url, current_time + cache_time)
        return url
    return None


# --- Извлечение видео из поста Telegram ---
def extract_video_url_from_telegram_post(post_url):
    """Извлекает прямую ссылку на видео из поста Telegram."""
    try:
        post_url = (post_url or "").strip()
        public_match = re.search(r'https?://t\.me/([^/\s]+)/(\d+)', post_url)
        private_match = re.search(r'https?://t\.me/c/(\d+)/(\d+)', post_url)

        chat_id_or_username = None
        message_id = None

        if public_match:
            chat_id_or_username = "@" + public_match.group(1)
            message_id = int(public_match.group(2))
        elif private_match:
            raw_id = int(private_match.group(1))
            chat_id_or_username = -1000000000000 - raw_id
            message_id = int(private_match.group(2))
        else:
            return None, "Неверный формат ссылки на пост Telegram."

        bot = Bot(token=TOKEN)
        message = None

        try:
            forwarded = bot.forward_message(
                chat_id=chat_id_or_username,
                from_chat_id=chat_id_or_username,
                message_id=message_id
            )
            message = forwarded
        except Exception:
            YOUR_ADMIN_CHAT_ID = int(os.environ.get('YOUR_ADMIN_CHAT_ID', -1003045387627))
            try:
                forwarded = bot.forward_message(
                    chat_id=YOUR_ADMIN_CHAT_ID,
                    from_chat_id=chat_id_or_username,
                    message_id=message_id
                )
                message = forwarded
            except Exception as e:
                return None, "Не удалось получить доступ к посту. Бот должен быть админом."

        if not message or not getattr(message, 'video', None):
            return None, "Видео не найдено в посте."

        file_id = message.video.file_id
        direct_url = get_cached_direct_video_url(file_id)
        if not direct_url:
            return None, "Не удалось получить прямую ссылку на видео."

        return direct_url, None
    except Exception as e:
        logger.error(f"Ошибка извлечения видео: {e}", exc_info=True)
        return None, f"Ошибка: {str(e)}"


def extract_video_url_sync(post_url):
    try:
        return extract_video_url_from_telegram_post(post_url)
    except Exception as e:
        logger.error(f"Ошибка в extract_video_url_sync: {e}", exc_info=True)
        return None, f"Ошибка: {e}"


# --- Telegram Bot Init ---
if TOKEN:
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    def start(update, context):
        # Проверка наличия сообщения
        if not update or not update.message:
            logger.warning("Получен update без сообщения в start()")
            return
            
        user = update.message.from_user
        telegram_id = str(user.id)
        get_or_create_user(
            telegram_id=telegram_id,
            username=getattr(user, 'username', None),
            first_name=getattr(user, 'first_name', None),
            last_name=getattr(user, 'last_name', None)
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
    extra = {}
    for row in data:
        item_id = row[0]
        reactions = get_reactions_count(item_type_plural, item_id) or {'like': 0, 'dislike': 0, 'star': 0, 'fire': 0}
        comments_count = len(get_comments(item_type_plural, item_id) or [])
        extra[item_id] = {'reactions': reactions, 'comments_count': comments_count}
    return extra


# --- ИСПРАВЛЕННЫЕ МАРШРУТЫ ---
@app.route('/moments')
def moments():
    try:
        cached = cache_get('moments_list')
        if cached:
            logger.info("moments_list загружен из кэша")
            return render_template('moments.html', moments=cached)

        logger.info("Получение всех моментов из БД...")
        data = get_all_moments() or []
        logger.info(f"Получено {len(data)} моментов")

        extra_map = build_extra_map(data, 'moments')

        combined_data = []
        for row in data:  # <-- ИСПРАВЛЕНО: было "for row in"
            item_dict = {
                'id': row[0],
                'title': row[1],
                'description': row[2],
                'video_url': row[3],
                'created_at': row[4] if len(row) > 4 else None
            }
            extra = extra_map.get(row[0], {
                'reactions': {'like': 0, 'dislike': 0, 'star': 0, 'fire': 0},
                'comments_count': 0
            })
            item_dict.update(extra)
            combined_data.append(item_dict)

        cache_set('moments_list', combined_data, expire=600)
        return render_template('moments.html', moments=combined_data)

    except Exception as e:
        logger.error(f"Ошибка в /moments: {e}", exc_info=True)
        return render_template('moments.html', moments=[]), 500


@app.route('/trailers')
def trailers():
    try:
        cached = cache_get('trailers_list')
        if cached:
            logger.info("trailers_list загружен из кэша")
            return render_template('trailers.html', trailers=cached)

        logger.info("Получение всех трейлеров из БД...")
        data = get_all_trailers() or []
        logger.info(f"Получено {len(data)} трейлеров")

        extra_map = build_extra_map(data, 'trailers')

        combined_data = []
        for row in data:  # <-- ИСПРАВЛЕНО: было "for row in"
            item_dict = {
                'id': row[0],
                'title': row[1],
                'description': row[2],
                'video_url': row[3],
                'created_at': row[4] if len(row) > 4 else None
            }
            extra = extra_map.get(row[0], {
                'reactions': {'like': 0, 'dislike': 0, 'star': 0, 'fire': 0},
                'comments_count': 0
            })
            item_dict.update(extra)
            combined_data.append(item_dict)

        cache_set('trailers_list', combined_data, expire=600)
        return render_template('trailers.html', trailers=combined_data)

    except Exception as e:
        logger.error(f"Ошибка в /trailers: {e}", exc_info=True)
        return render_template('trailers.html', trailers=[]), 500


@app.route('/news')
def news():
    try:
        cached = cache_get('news_list')
        if cached:
            logger.info("news_list загружен из кэша")
            return render_template('news.html', news=cached)

        logger.info("Получение всех новостей из БД...")
        data = get_all_news() or []
        logger.info(f"Получено {len(data)} новостей")

        extra_map = build_extra_map(data, 'news')

        combined_data = []
        for row in data:  # <-- ИСПРАВЛЕНО: было "for row in"
            item_dict = {
                'id': row[0],
                'title': row[1],
                'text': row[2],  # важно: в шаблоне используется {{ news_item.text }}
                'image_url': row[3],
                'created_at': row[4] if len(row) > 4 else None
            }
            extra = extra_map.get(row[0], {
                'reactions': {'like': 0, 'dislike': 0, 'star': 0, 'fire': 0},
                'comments_count': 0
            })
            item_dict.update(extra)
            combined_data.append(item_dict)

        cache_set('news_list', combined_data, expire=600)
        return render_template('news.html', news=combined_data)

    except Exception as e:
        logger.error(f"Ошибка в /news: {e}", exc_info=True)
        return render_template('news.html', news=[]), 500


# --- Остальные маршруты ---
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/moments/<int:item_id>')
def moment_detail(item_id):
    item = get_item_by_id('moments', item_id)
    if not item:
        abort(404)
    reactions = get_reactions_count('moments', item_id)
    comments = get_comments('moments', item_id)
    return render_template('moment_detail.html', item=item, reactions=reactions, comments=comments)


@app.route('/trailers/<int:item_id>')
def trailer_detail(item_id):
    item = get_item_by_id('trailers', item_id)
    if not item:
        abort(404)
    reactions = get_reactions_count('trailers', item_id)
    comments = get_comments('trailers', item_id)
    return render_template('trailer_detail.html', item=item, reactions=reactions, comments=comments)


@app.route('/news/<int:item_id>')
def news_detail(item_id):
    item = get_item_by_id('news', item_id)
    if not item:
        abort(404)
    reactions = get_reactions_count('news', item_id)
    comments = get_comments('news', item_id)
    return render_template('news_detail.html', item=item, reactions=reactions, comments=comments)


# --- API ---
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

        if video_url and 't.me/' in video_url:
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
            return jsonify(success=False, error="Укажите ссылку или загрузите файл"), 400

        add_moment(title, desc, video_url)
        cache_delete('moments_list')
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

        if video_url and 't.me/' in video_url:
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
            return jsonify(success=False, error="Укажите ссылку или загрузите файл"), 400

        add_trailer(title, desc, video_url)
        cache_delete('trailers_list')
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"API add_trailer error: {e}", exc_info=True)
        return jsonify(success=False, error=str(e)), 500


@app.route('/api/add_news', methods=['POST'])
def api_add_news():
    try:
        payload = _get_payload()
        title = payload.get('title', '').strip()
        text = payload.get('text', '').strip()
        image_url = payload.get('image_url', '').strip()

        if not image_url and 'image_file' in request.files:
            saved = save_uploaded_file(request.files['image_file'], ALLOWED_IMAGE_EXTENSIONS)
            if saved:
                image_url = saved

        add_news(title, text, image_url)
        cache_delete('news_list')
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


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/admin')
@admin_required
def admin_dashboard():
    stats = get_stats()
    return render_template('admin/dashboard.html', **stats)


@app.route('/admin/add_video')
@admin_required
def admin_add_video_form():
    return render_template('admin/add_video.html')


@app.route('/admin/content')
@admin_required
def admin_content():
    return render_template(
        'admin/content.html',
        moments=get_all_moments() or [],
        trailers=get_all_trailers() or [],
        news=get_all_news() or []
    )


@app.route('/admin/delete/<content_type>/<int:content_id>')
@admin_required
def admin_delete(content_type, content_id):
    mapping = {
        'moment': ('moments', delete_item),
        'trailer': ('trailers', delete_item),
        'news': ('news', delete_item)
    }
    if content_type in mapping:
        item_type, func = mapping[content_type]
        func(item_type, content_id)
        cache_delete(f'{item_type}_list')
    return redirect(url_for('admin_content'))


@app.route('/admin/access')
@admin_required
def admin_access_settings():
    return render_template(
        'admin/access/settings.html',
        moment_roles=get_access_settings('moment'),
        trailer_roles=get_access_settings('trailer'),
        news_roles=get_access_settings('news')
    )


@app.route('/admin/access/update/<content_type>', methods=['POST'])
@admin_required
def admin_update_access(content_type):
    roles = request.form.getlist('roles')
    update_access_settings(content_type, roles)
    return redirect(url_for('admin_access_settings'))


@app.route('/admin/add_video_json', methods=['POST'])
@admin_required
def admin_add_video_json():
    try:
        data = request.get_json()
        if not data:
            return jsonify(success=False, error="Неверный JSON"), 400

        title = data.get('title', '').strip()
        desc = data.get('description', '').strip()
        category = data.get('category', '').strip()
        post_link = data.get('post_link', '').strip()

        if not title or not post_link or category not in ['moment', 'trailer', 'news']:
            return jsonify(success=False, error="Неверные данные"), 400

        video_url = post_link
        if 't.me/' in post_link:
            direct_url, error = extract_video_url_sync(post_link)
            if direct_url:
                video_url = direct_url
            else:
                return jsonify(success=False, error=error), 400

        if category == 'moment':
            add_moment(title, desc, video_url)
            cache_delete('moments_list')
        elif category == 'trailer':
            add_trailer(title, desc, video_url)
            cache_delete('trailers_list')
        elif category == 'news':
            add_news(title, desc, video_url if video_url.startswith('http') else None)
            cache_delete('news_list')

        return jsonify(success=True)
    except Exception as e:
        logger.error(f"admin_add_video_json error: {e}", exc_info=True)
        return jsonify(success=False, error=str(e)), 500


# --- Telegram Handlers ---
def add_video_command(update, context):
    # Проверка наличия сообщения и текста
    if not update or not update.message or not update.message.text:
        logger.warning("Получен update без сообщения или текста в add_video_command()")
        return
        
    user = update.message.from_user
    telegram_id = str(user.id)
    role = get_user_role(telegram_id)
    if role not in ['owner', 'admin']:
        update.message.reply_text("❌ У вас нет прав.")
        return
    parts = update.message.text.split(' ', 2)
    if len(parts) < 3 or parts[1].lower() not in ['moment', 'trailer', 'news']:
        update.message.reply_text("❌ Формат: /add_video [moment|trailer|news] [название]")
        return
    pending_video_data[telegram_id] = {'content_type': parts[1].lower(), 'title': parts[2]}
    update.message.reply_text(f"🎬 Добавление '{parts[1]}' с названием '{parts[2]}'. Пришлите видео.")


def handle_pending_video_text(update, context):
    # Проверка наличия сообщения и текста
    if not update or not update.message or not update.message.text:
        logger.warning("Получен update без сообщения или текста в handle_pending_video_text()")
        return
        
    user = update.message.from_user
    telegram_id = str(user.id)
    if telegram_id not in pending_video_data:
        return
    data = pending_video_data.pop(telegram_id)
    content_type, title = data['content_type'], data['title']
    video_url = update.message.text.strip()
    if not video_url.startswith('http'):
        update.message.reply_text("❌ Отправьте прямую ссылку.")
        pending_video_data[telegram_id] = data  # Возвращаем данные обратно
        return
    if content_type == 'moment':
        add_moment(title, "Добавлено через Telegram", video_url)
    elif content_type == 'trailer':
        add_trailer(title, "Добавлено через Telegram", video_url)
    elif content_type == 'news':
        add_news(title, "Добавлено через Telegram", video_url)
    update.message.reply_text(f"✅ {content_type} '{title}' добавлено!")
    cache_delete('moments_list')
    cache_delete('trailers_list')
    cache_delete('news_list')


def handle_pending_video_file(update, context):
    # Проверка наличия сообщения и видео
    if not update or not update.message or not getattr(update.message, 'video', None):
        logger.warning("Получен update без сообщения или видео в handle_pending_video_file()")
        return
        
    user = update.message.from_user
    telegram_id = str(user.id)
    if telegram_id not in pending_video_data:
        return
    data = pending_video_data.pop(telegram_id)
    content_type, title = data['content_type'], data['title']
    file_id = update.message.video.file_id
    video_url = get_cached_direct_video_url(file_id)
    if not video_url:
        update.message.reply_text("❌ Не удалось получить ссылку.")
        pending_video_data[telegram_id] = data  # Возвращаем данные обратно
        return
    if content_type == 'moment':
        add_moment(title, "Добавлено через Telegram", video_url)
    elif content_type == 'trailer':
        add_trailer(title, "Добавлено через Telegram", video_url)
    elif content_type == 'news':
        add_news(title, "Добавлено через Telegram", video_url)
    update.message.reply_text(f"✅ {content_type} '{title}' добавлено!")
    cache_delete('moments_list')
    cache_delete('trailers_list')
    cache_delete('news_list')


if dp:
    dp.add_handler(CommandHandler('add_video', add_video_command))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_pending_video_text))
    dp.add_handler(MessageHandler(Filters.video & ~Filters.command, handle_pending_video_file))


# --- Telegram Webhook Route (NEW) ---
@app.route(f'/{TOKEN}', methods=['POST'])
def telegram_webhook():
    """Обработка Telegram Webhook."""
    if not updater:
        logger.error("Updater не инициализирован")
        return "Bot not initialized", 500

    try:
        json_string = request.get_data().decode('utf-8')
        from telegram import Update
        update = Update.de_json(json.loads(json_string), updater.bot)
        updater.dispatcher.process_update(update)
        return "OK", 200
    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}", exc_info=True)
        return "Error", 500


# --- Start Bot ---
def start_bot():
    if updater and TOKEN and WEBHOOK_URL:
        try:
            logger.info("Установка Telegram webhook...")
            webhook_url = f"{WEBHOOK_URL}/{TOKEN}"
            updater.bot.set_webhook(url=webhook_url)
            logger.info(f"Webhook установлен: {webhook_url}")
        except Exception as e:
            logger.error(f"Ошибка установки webhook: {e}", exc_info=True)
    elif updater:
        logger.info("Запуск Telegram бота (polling)...")
        updater.start_polling()


# --- Main ---
if __name__ == '__main__':
    try:
        init_db()
        logger.info("База данных инициализирована.")
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")

    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()

    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
