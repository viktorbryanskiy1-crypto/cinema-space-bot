import os
import threading
import logging
import uuid
from datetime import datetime
from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, session, send_from_directory, abort
)
from werkzeug.utils import secure_filename
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, Update
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

# --- Обёртки для удаления ---
def delete_moment(item_id):
    delete_item('moments', item_id)

def delete_trailer(item_id):
    delete_item('trailers', item_id)

def delete_news(item_id):
    delete_item('news', item_id)

# --- Logging ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Config ---
TOKEN = os.environ.get('TELEGRAM_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://yourdomain.com').strip()
REDIS_URL = os.environ.get('REDIS_URL', None)
if not TOKEN:
    logger.error("TELEGRAM_TOKEN not set!")
    # Не завершаем процесс под gunicorn, чтобы сайт работал без бота
    # но для локального запуска лучше явно экспортировать токен.
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

# --- Telegram Bot (v13) ---
updater = None
dp = None
pending_video_data = {}

if TOKEN:
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    def start(update, context):
        try:
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
            logger.info(f"/start from {telegram_id}")
        except Exception as e:
            logger.error(f"Error in /start: {e}")

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
            f"Пришли прямой URL видео (https://...) или просто отправь видео файлом."
        )
        logger.info(f"User {telegram_id} adding video: {parts[1]} - {parts[2]}")

    def handle_pending_video_text(update, context):
        """Пользователь прислал текст — пытаемся принять как прямой URL.
        Ссылки на пост t.me парсить ботом нельзя (Bot API не даёт получить произвольное сообщение по ссылке).
        В этом случае лучше отправить само видео боту (файлом) — бот возьмёт стабильный file_url.
        """
        user = update.message.from_user
        telegram_id = str(user.id)
        if telegram_id not in pending_video_data:
            return

        data = pending_video_data.pop(telegram_id)
        content_type, title = data['content_type'], data['title']
        desc = "Added via Telegram bot (text URL)"
        text = update.message.text.strip()
        video_url = text

        try:
            if not (video_url.startswith('http://') or video_url.startswith('https://')):
                update.message.reply_text("❌ Это не URL. Пришли прямую ссылку на видео или отправь файл видео.")
                pending_video_data[telegram_id] = data
                return

            if content_type == 'moment':
                add_moment(title, desc, video_url)
            elif content_type == 'trailer':
                add_trailer(title, desc, video_url)
            elif content_type == 'news':
                add_news(title, desc, video_url)

            update.message.reply_text(f"✅ '{content_type}' '{title}' добавлено по ссылке!")
            cache_delete('moments_list')
            cache_delete('trailers_list')
            cache_delete('news_list')
        except Exception as e:
            logger.error(f"Ошибка при добавлении видео (text): {e}")
            update.message.reply_text(f"❌ Ошибка: {e}")
            pending_video_data[telegram_id] = data

    def handle_pending_video_file(update, context):
        """Пользователь прислал именно файл (video). Берём стабильный file_path через getFile."""
        user = update.message.from_user
        telegram_id = str(user.id)
        if telegram_id not in pending_video_data:
            return

        data = pending_video_data.pop(telegram_id)
        content_type, title = data['content_type'], data['title']
        desc = "Added via Telegram bot (file)"

        try:
            if not update.message.video:
                update.message.reply_text("❌ Это не видео. Пришли файл видео или ссылку.")
                pending_video_data[telegram_id] = data
                return

            file_obj = context.bot.get_file(update.message.video.file_id)
            # В PTB v13 file_obj.file_path уже содержит полный стабильный URL
            video_url = file_obj.file_path

            if content_type == 'moment':
                add_moment(title, desc, video_url)
            elif content_type == 'trailer':
                add_trailer(title, desc, video_url)
            elif content_type == 'news':
                add_news(title, desc, video_url)

            update.message.reply_text(f"✅ '{content_type}' '{title}' добавлено из файла!")
            cache_delete('moments_list')
            cache_delete('trailers_list')
            cache_delete('news_list')
        except Exception as e:
            logger.error(f"Ошибка при добавлении видео (file): {e}")
            update.message.reply_text(f"❌ Ошибка: {e}")
            pending_video_data[telegram_id] = data

    # Подключение обработчиков к боту
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('add_video', add_video_command))
    dp.add_handler(MessageHandler(Filters.video & ~Filters.command, handle_pending_video_file))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_pending_video_text))

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    if not updater:
        return 'bot disabled', 200
    update = Update.de_json(request.get_json(force=True), updater.bot)
    updater.dispatcher.process_update(update)
    return 'ok'

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
    """
    data: список кортежей (id, title, description, video_or_image_url, created_at)
    возвращает словарь { id: {reactions: {...}, comments_count: N} }
    """
    extra = {}
    for row in data:
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
    cached = cache_get('moments_list')
    if cached:
        logger.info(f"/moments from cache: {len(cached)} items")
        # cached хранит обогащённые данные в некоторых прежних версиях — подстрахуем шаблон
        return render_template('moments.html', moments=cached, extra_by_id={})

    data = get_all_moments() or []  # список кортежей
    logger.info(f"/moments from DB: {len(data)} items")
    extra_map = build_extra_map(data, 'moments')
    cache_set('moments_list_raw_count', len(data), expire=120)  # вспомогательно
    return render_template('moments.html', moments=data, extra_by_id=extra_map)

@app.route('/trailers')
def trailers():
    cached = cache_get('trailers_list')
    if cached:
        logger.info(f"/trailers from cache: {len(cached)} items")
        return render_template('trailers.html', trailers=cached, extra_by_id={})

    data = get_all_trailers() or []
    logger.info(f"/trailers from DB: {len(data)} items")
    extra_map = build_extra_map(data, 'trailers')
    cache_set('trailers_list_raw_count', len(data), expire=120)
    return render_template('trailers.html', trailers=data, extra_by_id=extra_map)

@app.route('/news')
def news():
    cached = cache_get('news_list')
    if cached:
        logger.info(f"/news from cache: {len(cached)} items")
        return render_template('news.html', news=cached, extra_by_id={})

    data = get_all_news() or []
    logger.info(f"/news from DB: {len(data)} items")
    extra_map = build_extra_map(data, 'news')
    cache_set('news_list_raw_count', len(data), expire=120)
    return render_template('news.html', news=data, extra_by_id=extra_map)

# --- Детальные страницы (если используются) ---
@app.route('/moments/<int:item_id>')
def moment_detail(item_id):
    item = get_item_by_id('moments', item_id)
    if not item: abort(404)
    reactions = get_reactions_count('moments', item_id)
    comments = get_comments('moments', item_id)
    return render_template('moment_detail.html', item=item, reactions=reactions, comments=comments)

@app.route('/trailers/<int:item_id>')
def trailer_detail(item_id):
    item = get_item_by_id('trailers', item_id)
    if not item: abort(404)
    reactions = get_reactions_count('trailers', item_id)
    comments = get_comments('trailers', item_id)
    return render_template('trailer_detail.html', item=item, reactions=reactions, comments=comments)

@app.route('/news/<int:item_id>')
def news_detail(item_id):
    item = get_item_by_id('news', item_id)
    if not item: abort(404)
    reactions = get_reactions_count('news', item_id)
    comments = get_comments('news', item_id)
    return render_template('news_detail.html', item=item, reactions=reactions, comments=comments)

# --- API: добавление контента (универсально принимает JSON или форму) ---
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

        # также принимаем файл (на будущее, если понадобится локалка)
        if 'video_file' in request.files and not video_url:
            saved = save_uploaded_file(request.files['video_file'], ALLOWED_VIDEO_EXTENSIONS)
            if saved: video_url = saved

        add_moment(title, desc, video_url)
        cache_delete('moments_list')
        logger.info(f"api_add_moment: inserted '{title}'")
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"API add_moment error: {e}")
        return jsonify(success=False, error=str(e)), 500

@app.route('/api/add_trailer', methods=['POST'])
def api_add_trailer():
    try:
        payload = _get_payload()
        title = payload.get('title', '').strip()
        desc = payload.get('description', '').strip()
        video_url = payload.get('video_url', '').strip()

        if 'video_file' in request.files and not video_url:
            saved = save_uploaded_file(request.files['video_file'], ALLOWED_VIDEO_EXTENSIONS)
            if saved: video_url = saved

        add_trailer(title, desc, video_url)
        cache_delete('trailers_list')
        logger.info(f"api_add_trailer: inserted '{title}'")
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"API add_trailer error: {e}")
        return jsonify(success=False, error=str(e)), 500

@app.route('/api/add_news', methods=['POST'])
def api_add_news():
    try:
        payload = _get_payload()
        title = payload.get('title', '').strip()
        text = payload.get('text', payload.get('description', '')).strip()
        image_url = payload.get('image_url', '').strip()

        if 'image_file' in request.files and not image_url:
            saved = save_uploaded_file(request.files['image_file'], ALLOWED_IMAGE_EXTENSIONS)
            if saved: image_url = saved

        add_news(title, text, image_url)
        cache_delete('news_list')
        logger.info(f"api_add_news: inserted '{title}'")
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"API add_news error: {e}")
        return jsonify(success=False, error=str(e)), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- Reactions & Comments ---
@app.route('/api/reaction', methods=['POST'])
def api_add_reaction():
    try:
        data = request.get_json(force=True)
        item_type = data.get('item_type')  # ожидание: 'moments'|'trailers'|'news'
        item_id = int(data.get('item_id'))
        user_id = data.get('user_id', 'anonymous')
        reaction = data.get('reaction')
        success = add_reaction(item_type, item_id, user_id, reaction)
        return jsonify(success=success)
    except Exception as e:
        logger.error(f"API add_reaction error: {e}")
        return jsonify(success=False, error=str(e)), 500

@app.route('/api/comments', methods=['GET'])
def api_get_comments():
    try:
        item_type = request.args.get('type')  # 'moments'|'trailers'|'news'
        item_id = int(request.args.get('id'))
        comments = get_comments(item_type, item_id)
        return jsonify(comments=comments)
    except Exception as e:
        logger.error(f"API get_comments error: {e}")
        return jsonify(comments=[], error=str(e)), 500

@app.route('/api/comment', methods=['POST'])
def api_add_comment():
    try:
        data = request.get_json(force=True)
        item_type = data.get('item_type')  # 'moments'|'trailers'|'news'
        item_id = int(data.get('item_id'))
        user_name = data.get('user_name', 'Гость')
        text = data.get('text')
        add_comment(item_type, item_id, user_name, text)
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"API add_comment error: {e}")
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

@app.route('/admin/content')
@admin_required
def admin_content():
    moments = get_all_moments() or []
    trailers = get_all_trailers() or []
    news = get_all_news() or []
    return render_template('admin/content.html', moments=moments, trailers=trailers, news=news)

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
    logger.info(f"Updated access roles for {content_type}: {roles}")
    return redirect(url_for('admin_access_settings'))

# --- Новая панель «Добавить видео» ---
@app.route('/admin/add_video', methods=['GET'])
@admin_required
def admin_add_video():
    return render_template('admin/add_video.html')  # шаблон ты уже добавил ранее

# --- Запуск бота (локально) ---
def start_bot():
    if updater:
        updater.start_polling()
        updater.idle()

# --- Main ---
if __name__ == '__main__':
    try:
        init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ DB init error: {e}")
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
