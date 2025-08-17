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
def delete_moment(item_id): delete_item('moments', item_id)
def delete_trailer(item_id): delete_item('trailers', item_id)
def delete_news(item_id): delete_item('news', item_id)

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
    exit(1)

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
updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher
pending_video_data = {}

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
    update.message.reply_text(f"🎬 Adding '{parts[1]}' with title '{parts[2]}'. Send video URL.")
    logger.info(f"User {telegram_id} adding video: {parts[1]} - {parts[2]}")

# --- Telegram post URL обработка ---
def handle_pending_video_url(update, context):
    user = update.message.from_user
    telegram_id = str(user.id)
    if telegram_id not in pending_video_data:
        return

    text = update.message.text.strip()
    data = pending_video_data.pop(telegram_id)
    content_type, title = data['content_type'], data['title']
    desc = "Added via Telegram bot"

    try:
        video_url = text
        if content_type == 'moment': add_moment(title, desc, video_url)
        elif content_type == 'trailer': add_trailer(title, desc, video_url)
        elif content_type == 'news': add_news(title, desc, video_url)
        update.message.reply_text(f"✅ '{content_type}' '{title}' успешно добавлено!")
        cache_delete(f"{content_type}s_list" if content_type != 'news' else 'news_list')
    except Exception as e:
        logger.error(f"Ошибка при добавлении видео: {e}")
        update.message.reply_text(f"❌ Ошибка: {e}")
        pending_video_data[telegram_id] = data

# --- Подключение обработчиков ---
dp.add_handler(CommandHandler('start', start))
dp.add_handler(CommandHandler('add_video', add_video_command))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_pending_video_url))

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
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
    try: return json.loads(redis_client.get(key) or "null")
    except: return None

def cache_set(key, value, expire=300):
    if redis_client:
        try: redis_client.set(key, json.dumps(value), ex=expire)
        except: pass

def cache_delete(key):
    if redis_client:
        try: redis_client.delete(key)
        except: pass

def prepare_items_with_extra(data, item_type):
    result=[]
    for i in data:
        reactions=get_reactions_count(item_type+'s',i[0]) or {'like':0,'dislike':0,'star':0,'fire':0}
        comments_count=len(get_comments(item_type+'s',i[0]) or [])
        result.append({
            'id': i[0], 'title': i[1], 'description': i[2],
            'video_url': i[3] if item_type != 'news' else None,
            'image_url': i[3] if item_type == 'news' else None,
            'created_at': i[4], 'reactions': reactions, 'comments_count': comments_count
        })
    return result

# --- Routes ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/moments')
def moments():
    cached = cache_get('moments_list')
    if cached: return render_template('moments.html', moments=cached)
    data=get_all_moments() or []
    result=prepare_items_with_extra(data,'moment')
    cache_set('moments_list',result)
    return render_template('moments.html', moments=result)

@app.route('/trailers')
def trailers():
    cached = cache_get('trailers_list')
    if cached: return render_template('trailers.html', trailers=cached)
    data=get_all_trailers() or []
    result=prepare_items_with_extra(data,'trailer')
    cache_set('trailers_list',result)
    return render_template('trailers.html', trailers=result)

@app.route('/news')
def news():
    cached=cache_get('news_list')
    if cached: return render_template('news.html', news=cached)
    data=get_all_news() or []
    result=prepare_items_with_extra(data,'news')
    cache_set('news_list',result)
    return render_template('news.html', news=result)

# --- API: добавление контента из админки ---
@app.route('/api/add_moment',methods=['POST'])
def api_add_moment():
    try:
        data=request.json
        add_moment(data.get('title',''), data.get('description',''), data.get('video_url',''))
        cache_delete('moments_list')
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"API add_moment error: {e}")
        return jsonify(success=False,error=str(e))

@app.route('/api/add_trailer',methods=['POST'])
def api_add_trailer():
    try:
        data=request.json
        add_trailer(data.get('title',''), data.get('description',''), data.get('video_url',''))
        cache_delete('trailers_list')
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"API add_trailer error: {e}")
        return jsonify(success=False,error=str(e))

@app.route('/api/add_news',methods=['POST'])
def api_add_news():
    try:
        data=request.json
        add_news(data.get('title',''), data.get('description',''), data.get('video_url',''))
        cache_delete('news_list')
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"API add_news error: {e}")
        return jsonify(success=False,error=str(e))

# --- Admin routes ---
@app.route('/admin/login',methods=['GET','POST'])
def admin_login():
    if request.method=='POST':
        if authenticate_admin(request.form.get('username',''), request.form.get('password','')):
            session['admin']=request.form['username']
            return redirect(url_for('admin_dashboard'))
        return render_template('admin/login.html',error='Неверный логин или пароль')
    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin',None)
    return redirect(url_for('admin_login'))

def admin_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args,**kwargs):
        if 'admin' not in session: return redirect(url_for('admin_login'))
        return func(*args,**kwargs)
    return wrapper

@app.route('/admin')
@admin_required
def admin_dashboard():
    stats=get_stats()
    return render_template('admin/dashboard.html',
        moments_count=stats.get('moments',0),
        trailers_count=stats.get('trailers',0),
        news_count=stats.get('news',0),
        comments_count=stats.get('comments',0))

# --- 📌 Новый маршрут для добавления видео ---
@app.route('/admin/add_video', methods=['GET','POST'])
@admin_required
def admin_add_video():
    if request.method == 'POST':
        content_type = request.form.get('type')
        title = request.form.get('title','')
        desc = request.form.get('description','')
        video_url = request.form.get('video_url','')

        try:
            if content_type == 'moment': add_moment(title, desc, video_url)
            elif content_type == 'trailer': add_trailer(title, desc, video_url)
            elif content_type == 'news': add_news(title, desc, video_url)
            cache_delete(f"{content_type}s_list" if content_type != 'news' else 'news_list')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            return render_template('admin/add_video.html', error=str(e))
    return render_template('admin/add_video.html')

# --- Run ---
def start_bot():
    updater.start_polling()
    updater.idle()

if __name__=='__main__':
    try: init_db(); logger.info("✅ Database initialized")
    except Exception as e: logger.error(f"❌ DB init error: {e}")
    bot_thread=threading.Thread(target=start_bot,daemon=True)
    bot_thread.start()
    port=int(os.environ.get('PORT',10000))
    app.run(host='0.0.0.0',port=port)
