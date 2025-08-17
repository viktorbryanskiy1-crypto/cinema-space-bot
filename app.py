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
# Импорт реальных функций из database.py
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
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
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

def handle_pending_video_url(update, context):
    user = update.message.from_user
    telegram_id = str(user.id)
    if telegram_id not in pending_video_data:
        return

    text = update.message.text.strip()
    data = pending_video_data.pop(telegram_id)
    content_type, title = data['content_type'], data['title']
    desc = "Added via Telegram bot"

    video_url = ''
    try:
        # --- Проверяем, ссылка ли это на пост Telegram ---
        if text.startswith("https://t.me/"):
            # разбор ссылки на чат и сообщение
            chat_id, message_id = extract_chat_message_id(text)
            message = context.bot.get_chat(chat_id).get_message(message_id)
            if message.video:
                file = context.bot.get_file(message.video.file_id)
                video_url = file.file_path
        else:
            video_url = text  # обычный URL

        # --- Добавляем в базу ---
        if content_type == 'moment':
            add_moment(title, desc, video_url)
        elif content_type == 'trailer':
            add_trailer(title, desc, video_url)
        elif content_type == 'news':
            add_news(title, desc, video_url)

        update.message.reply_text(f"✅ '{content_type}' '{title}' добавлено!")
        cache_delete(f"{content_type}s_list" if content_type != 'news' else 'news_list')

    except Exception as e:
        logger.error(f"Ошибка при добавлении видео: {e}")
        update.message.reply_text(f"❌ Ошибка: {e}")
        pending_video_data[telegram_id] = data

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

# --- Detail pages ---
@app.route('/moments/<int:item_id>')
def moment_detail(item_id):
    item=get_item_by_id('moments',item_id)
    if not item: abort(404)
    reactions=get_reactions_count('moments',item_id)
    comments=get_comments('moments',item_id)
    return render_template('moment_detail.html',item=item,reactions=reactions,comments=comments)

@app.route('/trailers/<int:item_id>')
def trailer_detail(item_id):
    item=get_item_by_id('trailers',item_id)
    if not item: abort(404)
    reactions=get_reactions_count('trailers',item_id)
    comments=get_comments('trailers',item_id)
    return render_template('trailer_detail.html',item=item,reactions=reactions,comments=comments)

@app.route('/news/<int:item_id>')
def news_detail(item_id):
    item=get_item_by_id('news',item_id)
    if not item: abort(404)
    reactions=get_reactions_count('news',item_id)
    comments=get_comments('news',item_id)
    return render_template('news_detail.html',item=item,reactions=reactions,comments=comments)

# --- API for adding content ---
@app.route('/api/add_moment',methods=['POST'])
def api_add_moment():
    try:
        video_url=''
        if 'video_file' in request.files: video_url=save_uploaded_file(request.files['video_file'],ALLOWED_VIDEO_EXTENSIONS) or ''
        data=request.form if request.form else (request.json if request.is_json else {})
        add_moment(data.get('title',''),data.get('description',''),video_url)
        cache_delete('moments_list')
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"API add_moment error: {e}")
        return jsonify(success=False,error=str(e))

@app.route('/api/add_trailer',methods=['POST'])
def api_add_trailer():
    try:
        video_url=''
        if 'video_file' in request.files: video_url=save_uploaded_file(request.files['video_file'],ALLOWED_VIDEO_EXTENSIONS) or ''
        data=request.form if request.form else (request.json if request.is_json else {})
        add_trailer(data.get('title',''),data.get('description',''),video_url)
        cache_delete('trailers_list')
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"API add_trailer error: {e}")
        return jsonify(success=False,error=str(e))

@app.route('/api/add_news',methods=['POST'])
def api_add_news():
    try:
        title,text,image_url='','',''
        if request.is_json:
            title=request.json.get('title',''); text=request.json.get('text',''); image_url=request.json.get('image_url','')
        else: title=request.form.get('title',''); text=request.form.get('text','')
        if 'image_file' in request.files: image_url=save_uploaded_file(request.files['image_file'],ALLOWED_IMAGE_EXTENSIONS) or ''
        if not image_url and 'image_url' in request.form: image_url=request.form['image_url']
        add_news(title,text,image_url)
        cache_delete('news_list')
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"API add_news error: {e}")
        return jsonify(success=False,error=str(e))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'],filename)

# --- Reactions & Comments ---
@app.route('/api/reaction',methods=['POST'])
def api_add_reaction():
    try:
        data=request.json
        success=add_reaction(data.get('item_type'),data.get('item_id'),data.get('user_id','anonymous'),data.get('reaction'))
        return jsonify(success=success)
    except Exception as e:
        logger.error(f"API add_reaction error: {e}")
        return jsonify(success=False,error=str(e))

@app.route('/api/comments',methods=['GET'])
def api_get_comments():
    try:
        item_type=request.args.get('type')
        item_id=request.args.get('id')
        comments=get_comments(item_type,int(item_id))
        return jsonify(comments=comments)
    except Exception as e:
        logger.error(f"API get_comments error: {e}")
        return jsonify(comments=[],error=str(e))

@app.route('/api/comment',methods=['POST'])
def api_add_comment():
    try:
        data=request.json
        add_comment(data.get('item_type'),data.get('item_id'),data.get('user_name','Гость'),data.get('text'))
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"API add_comment error: {e}")
        return jsonify(success=False,error=str(e))

# --- Admin ---
@app.route('/admin/login',methods=['GET','POST'])
def admin_login():
    if request.method=='POST':
        username=request.form.get('username','')
        password=request.form.get('password','')
        if authenticate_admin(username,password):
            session['admin']=username
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

@app.route('/admin/content')
@admin_required
def admin_content():
    moments=get_all_moments()
    trailers=get_all_trailers()
    news=get_all_news()
    return render_template('admin/content.html',moments=moments,trailers=trailers,news=news)

@app.route('/admin/delete/<content_type>/<int:content_id>')
@admin_required
def admin_delete(content_type,content_id):
    if content_type=='moment': delete_moment(content_id); cache_delete('moments_list')
    elif content_type=='trailer': delete_trailer(content_id); cache_delete('trailers_list')
    elif content_type=='news': delete_news(content_id); cache_delete('news_list')
    return redirect(url_for('admin_content'))

@app.route('/admin/access')
@admin_required
def admin_access_settings():
    moment_roles=get_access_settings('moment')
    trailer_roles=get_access_settings('trailer')
    news_roles=get_access_settings('news')
    return render_template('admin/access/settings.html',
        moment_roles=moment_roles,trailer_roles=trailer_roles,news_roles=news_roles)

@app.route('/admin/access/update/<content_type>',methods=['POST'])
@admin_required
def admin_update_access(content_type):
    roles=request.form.getlist('roles')
    update_access_settings(content_type,roles)
    logger.info(f"Updated access roles for {content_type}: {roles}")
    return redirect(url_for('admin_access_settings'))

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
