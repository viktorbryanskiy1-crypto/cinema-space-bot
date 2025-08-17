# app.py
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

# Импортируем конкретные функции из database.py (как у тебя было)
from database import (
    get_or_create_user, get_user_role,
    add_moment, add_trailer, add_news,
    get_all_moments, get_all_trailers, get_all_news,
    get_reactions_count, get_comments,
    add_reaction, add_comment,
    authenticate_admin, get_stats,
    delete_moment, delete_trailer, delete_news,
    get_access_settings, update_access_settings,
    init_db, get_item_by_id  # предполагается, что эта функция есть в database.py
)

# Дополнительно импортируем модуль database для фолбэков (если понадобится)
import database as db_module

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Config ---
TOKEN = os.environ.get('TELEGRAM_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://cinema-space-bot.onrender.com').strip()
REDIS_URL = os.environ.get('REDIS_URL', None)

if not TOKEN:
    logger.error("TELEGRAM_TOKEN not set! Exiting.")
    exit(1)

# --- Redis (опционально, тихо падаем на None) ---
redis_client = None
if REDIS_URL:
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        redis_client.ping()
        logger.info("✅ Redis connected via REDIS_URL")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}. Continuing without Redis.")
        redis_client = None
else:
    try:
        redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        redis_client.ping()
        logger.info("✅ Local Redis connected")
    except Exception as e:
        logger.warning(f"Local Redis not available: {e}. Continuing without Redis.")
        redis_client = None

# --- Flask app ---
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'super-secret-key-change-me')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB per upload
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename, allowed_exts):
    return bool(filename and '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_exts)

# --- Telegram bot setup ---
updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher
pending_video_data = {}  # временное хранилище для /add_video (telegram_id -> {content_type, title})

def start(update, context):
    try:
        user = update.message.from_user
        telegram_id = str(user.id)
        # создаём/обновляем пользователя в БД
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
        logger.exception(f"Error in /start: {e}")

def add_video_command(update, context):
    try:
        user = update.message.from_user
        telegram_id = str(user.id)
        role = get_user_role(telegram_id)
        if role not in ['owner', 'admin']:
            update.message.reply_text("❌ У вас нет прав для добавления контента.")
            return
        text = update.message.text or ''
        parts = text.split(' ', 2)
        if len(parts) < 3 or parts[1].lower() not in ['moment', 'trailer', 'news']:
            update.message.reply_text("❌ Формат: /add_video [moment|trailer|news] [название]")
            return
        pending_video_data[telegram_id] = {'content_type': parts[1].lower(), 'title': parts[2]}
        update.message.reply_text(f"🎬 Добавление '{parts[1]}' с заголовком '{parts[2]}'. Пришлите, пожалуйста, ссылку на видео или отправьте файл.")
        logger.info(f"User {telegram_id} started adding {parts[1]}: {parts[2]}")
    except Exception as e:
        logger.exception(f"Error in add_video_command: {e}")
        update.message.reply_text("❌ Внутренняя ошибка команды.")

def handle_pending_video_url(update, context):
    try:
        user = update.message.from_user
        telegram_id = str(user.id)
        if telegram_id not in pending_video_data:
            return
        # если сообщение содержит документ/видео — скачиваем (необязательно реализовано)
        # В текущей реализации принимаем текстовую ссылку
        text = update.message.text or ''
        if not text.strip():
            update.message.reply_text("❌ Ссылка/URL не может быть пустой. Попробуйте ещё раз.")
            return
        data = pending_video_data.pop(telegram_id)
        ct = data['content_type']
        title = data['title']
        desc = "Добавлено через Telegram бот"
        if ct == 'moment':
            add_moment(title, desc, text.strip())
        elif ct == 'trailer':
            add_trailer(title, desc, text.strip())
        elif ct == 'news':
            # Если у тебя есть поддержка блоков — можно отправлять блоки, но здесь простой вариант.
            add_news(title, text.strip(), '')
        update.message.reply_text(f"✅ '{ct}' '{title}' успешно добавлен!")
        cache_delete(f"{ct}s_list" if ct != 'news' else 'news_list')
    except Exception as e:
        logger.exception(f"Error in handle_pending_video_url: {e}")
        # если упало — сохраняем обратно, чтобы пользователь мог повторить
        try:
            pending_video_data[telegram_id] = data
        except:
            pass
        update.message.reply_text(f"❌ Ошибка при добавлении: {e}")

dp.add_handler(CommandHandler('start', start))
dp.add_handler(CommandHandler('add_video', add_video_command))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_pending_video_url))

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    # Можно принимать обновления от Telegram (если используешь webhook)
    update = Update.de_json(request.get_json(force=True), updater.bot)
    updater.dispatcher.process_update(update)
    return 'ok'

# --- Helpers: files, cache, normalize items ---
def save_uploaded_file(file_storage, allowed_exts):
    if not file_storage or file_storage.filename == '':
        return None
    if not allowed_file(file_storage.filename, allowed_exts):
        return None
    filename = secure_filename(file_storage.filename)
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    file_storage.save(path)
    # возвращаем относительный URL, который отдаёт маршрут /uploads/<filename>
    return f"/uploads/{unique_name}"

def cache_get(key):
    if not redis_client:
        return None
    try:
        raw = redis_client.get(key)
        if not raw:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.debug(f"Redis GET error for {key}: {e}")
        return None

def cache_set(key, value, expire=300):
    if not redis_client:
        return
    try:
        redis_client.set(key, json.dumps(value), ex=expire)
    except Exception as e:
        logger.debug(f"Redis SET error for {key}: {e}")

def cache_delete(key):
    if not redis_client:
        return
    try:
        redis_client.delete(key)
    except Exception:
        pass

def truncate_text(text, length=180):
    if not text:
        return ''
    text = str(text)
    if len(text) <= length:
        return text
    return text[:length].rsplit(' ', 1)[0] + '…'

def normalize_db_row(row, item_type=None):
    """
    Принимает row (tuple или dict) и возвращает dict:
    {id, title, description, video_url, image_url, created_at, raw}
    raw — исходный объект
    """
    if row is None:
        return None
    if isinstance(row, dict):
        # ожидаем ключи: id, title, description/text, video_url/image_url, created_at
        nid = row.get('id')
        title = row.get('title') or row.get('name') or ''
        # text can be 'text' or 'description'
        description = row.get('text') if 'text' in row else row.get('description') if 'description' in row else ''
        video_url = row.get('video_url') if 'video_url' in row else None
        image_url = row.get('image_url') if 'image_url' in row else None
        created_at = row.get('created_at')
        # if blocks present (news with blocks)
        blocks = row.get('blocks') if 'blocks' in row else None
        return {
            'id': nid, 'title': title, 'description': description,
            'video_url': video_url, 'image_url': image_url,
            'created_at': created_at, 'raw': row, 'blocks': blocks
        }
    else:
        # tuple-like: предполагаем порядок [id, title, description/text, video_or_image, created_at]
        try:
            nid = row[0]
            title = row[1] if len(row) > 1 else ''
            description = row[2] if len(row) > 2 else ''
            fourth = row[3] if len(row) > 3 else None
            created_at = row[4] if len(row) > 4 else None
            # для news четвертый — image_url, для moment/trailer — video_url
            if item_type == 'news':
                return {
                    'id': nid, 'title': title, 'description': description,
                    'video_url': None, 'image_url': fourth,
                    'created_at': created_at, 'raw': row, 'blocks': None
                }
            else:
                return {
                    'id': nid, 'title': title, 'description': description,
                    'video_url': fourth, 'image_url': None,
                    'created_at': created_at, 'raw': row, 'blocks': None
                }
        except Exception:
            # если не можем распарсить — вернуть минимальный dict
            return {'id': None, 'title': str(row), 'description': '', 'video_url': None, 'image_url': None, 'created_at': None, 'raw': row, 'blocks': None}

def prepare_items_with_extra(data, item_type):
    """
    Принимает список строк из БД (tuple или dict) и возвращает список словарей,
    пригодных для шаблонов (preview).
    """
    result = []
    for r in data:
        item = normalize_db_row(r, item_type=item_type)
        try:
            reactions = get_reactions_count(item_type, item['id']) or {'like':0,'dislike':0,'star':0,'fire':0}
        except Exception:
            reactions = {'like':0,'dislike':0,'star':0,'fire':0}
        try:
            comments = get_comments(item_type, item['id']) or []
            comments_count = len(comments)
        except Exception:
            comments_count = 0

        preview_text = ''
        # Если у новости есть блоки, попробуем взять первый текстовый блок
        blocks = item.get('blocks')
        if blocks and isinstance(blocks, (list, tuple)) and len(blocks) > 0:
            # blocks может содержать dicts с keys block_type, content
            first_text = None
            for b in blocks:
                bt = b.get('block_type') if isinstance(b, dict) else (b[0] if len(b)>0 else None)
                content = b.get('content') if isinstance(b, dict) else (b[1] if len(b)>1 else '')
                if bt == 'text':
                    first_text = content
                    break
            preview_text = truncate_text(first_text or item.get('description') or '')
        else:
            preview_text = truncate_text(item.get('description') or '')

        result.append({
            'id': item.get('id'),
            'title': item.get('title'),
            'preview': preview_text,
            'video_url': item.get('video_url'),
            'image_url': item.get('image_url'),
            'created_at': item.get('created_at'),
            'reactions': reactions,
            'comments_count': comments_count
        })
    return result

# --- Fetch single item helper (используем get_item_by_id если есть, иначе fallback) ---
def fetch_item(item_type, item_id):
    """
    Возвращает normalized item dict или None.
    Попытается вызвать get_item_by_id (если есть), иначе возьмёт get_all_* и найдёт запись.
    Для новостей: попробует использовать get_news_with_blocks (если есть).
    """
    # Если в database есть get_item_by_id – используем
    try:
        if 'get_item_by_id' in globals():
            raw = get_item_by_id(item_type, item_id)
            if raw:
                # Если raw — простой dict с блоками, нормализуем
                item = normalize_db_row(raw, item_type=item_type)
                # если блоки нет, но есть отдельная функция get_news_with_blocks, попробуем получить блоки (для news)
                if item_type == 'news' and (not item.get('blocks') or item.get('blocks') is None):
                    try:
                        if hasattr(db_module, 'get_news_with_blocks'):
                            # получим все новости с блоками и найдем нужную
                            all_with_blocks = db_module.get_news_with_blocks()
                            for n in all_with_blocks:
                                if (isinstance(n, dict) and n.get('id') == item_id) or (isinstance(n, tuple) and n[0] == item_id):
                                    # нормализуем
                                    nb = normalize_db_row(n, item_type='news')
                                    return nb
                    except Exception:
                        pass
                return item
    except Exception as e:
        logger.debug(f"get_item_by_id failed: {e}")

    # Fallback — получить все и найти
    try:
        if item_type == 'moment':
            all_items = get_all_moments()
        elif item_type == 'trailer':
            all_items = get_all_trailers()
        elif item_type == 'news':
            # попробуем получить новости с блоками, если функция есть
            try:
                if hasattr(db_module, 'get_news_with_blocks'):
                    all_items = db_module.get_news_with_blocks()
                else:
                    all_items = get_all_news()
            except Exception:
                all_items = get_all_news()
        else:
            return None

        for r in all_items:
            # r может быть tuple или dict
            nid = r['id'] if isinstance(r, dict) else (r[0] if len(r)>0 else None)
            if nid == item_id:
                return normalize_db_row(r, item_type=item_type)
    except Exception as e:
        logger.exception(f"fetch_item fallback error: {e}")
    return None

# --- Routes (pages) ---
@app.route('/')
def index():
    # Можно передать свежую статистику, но пока простой рендер
    return render_template('index.html')

@app.route('/moments')
def moments():
    cached = cache_get('moments_list')
    if cached:
        return render_template('moments.html', moments=cached)
    try:
        data = get_all_moments() or []
    except Exception as e:
        logger.error(f"DB get_all_moments error: {e}")
        data = []
    result = prepare_items_with_extra(data, 'moment')
    cache_set('moments_list', result)
    return render_template('moments.html', moments=result)

@app.route('/trailers')
def trailers():
    cached = cache_get('trailers_list')
    if cached:
        return render_template('trailers.html', trailers=cached)
    try:
        data = get_all_trailers() or []
    except Exception as e:
        logger.error(f"DB get_all_trailers error: {e}")
        data = []
    result = prepare_items_with_extra(data, 'trailer')
    cache_set('trailers_list', result)
    return render_template('trailers.html', trailers=result)

@app.route('/news')
def news():
    cached = cache_get('news_list')
    if cached:
        return render_template('news.html', news=cached)
    # Попробуем получить новости с блоками, если функция в БД есть
    try:
        if hasattr(db_module, 'get_news_with_blocks'):
            data = db_module.get_news_with_blocks() or []
        else:
            data = get_all_news() or []
    except Exception as e:
        logger.error(f"DB get_all_news error: {e}")
        data = []
    result = prepare_items_with_extra(data, 'news')
    cache_set('news_list', result)
    return render_template('news.html', news=result)

# --- Detail pages (отдельная страница с видео/новостью + реакции + комментарии) ---
@app.route('/moments/<int:item_id>')
def moment_detail(item_id):
    item = fetch_item('moment', item_id)
    if not item:
        abort(404)
    try:
        reactions = get_reactions_count('moment', item_id) or {}
    except Exception:
        reactions = {}
    try:
        comments = get_comments('moment', item_id) or []
    except Exception:
        comments = []
    return render_template('moment_detail.html', item=item, reactions=reactions, comments=comments)

@app.route('/trailers/<int:item_id>')
def trailer_detail(item_id):
    item = fetch_item('trailer', item_id)
    if not item:
        abort(404)
    try:
        reactions = get_reactions_count('trailer', item_id) or {}
    except Exception:
        reactions = {}
    try:
        comments = get_comments('trailer', item_id) or []
    except Exception:
        comments = []
    return render_template('trailer_detail.html', item=item, reactions=reactions, comments=comments)

@app.route('/news/<int:item_id>')
def news_detail(item_id):
    item = fetch_item('news', item_id)
    if not item:
        abort(404)
    try:
        reactions = get_reactions_count('news', item_id) or {}
    except Exception:
        reactions = {}
    try:
        comments = get_comments('news', item_id) or []
    except Exception:
        comments = []
    # item может иметь поле blocks (если использовалась расширенная схема)
    blocks = item.get('blocks') if item else None
    return render_template('news_detail.html', item=item, blocks=blocks, reactions=reactions, comments=comments)

# --- API для добавления контента (WebApp / админ-панель) ---
@app.route('/api/add_moment', methods=['POST'])
def api_add_moment():
    try:
        video_url = ''
        if 'video_file' in request.files and request.files['video_file'].filename != '':
            video_url = save_uploaded_file(request.files['video_file'], ALLOWED_VIDEO_EXTENSIONS) or ''
        else:
            if request.is_json:
                video_url = request.json.get('video_url', '') or ''
            else:
                video_url = request.form.get('video_url', '') or ''
        # форма может быть form-data или json
        data = request.form if request.form else (request.json if request.is_json else {})
        title = data.get('title', '')
        description = data.get('description', '')
        add_moment(title, description, video_url)
        cache_delete('moments_list')
        return jsonify(success=True)
    except Exception as e:
        logger.exception(f"API add_moment error: {e}")
        return jsonify(success=False, error=str(e))

@app.route('/api/add_trailer', methods=['POST'])
def api_add_trailer():
    try:
        video_url = ''
        if 'video_file' in request.files and request.files['video_file'].filename != '':
            video_url = save_uploaded_file(request.files['video_file'], ALLOWED_VIDEO_EXTENSIONS) or ''
        else:
            if request.is_json:
                video_url = request.json.get('video_url', '') or ''
            else:
                video_url = request.form.get('video_url', '') or ''
        data = request.form if request.form else (request.json if request.is_json else {})
        title = data.get('title', '')
        description = data.get('description', '')
        add_trailer(title, description, video_url)
        cache_delete('trailers_list')
        return jsonify(success=True)
    except Exception as e:
        logger.exception(f"API add_trailer error: {e}")
        return jsonify(success=False, error=str(e))

@app.route('/api/add_news', methods=['POST'])
def api_add_news():
    """
    Поддерживаем два формата:
    1) Простая новость: title, text, image_file or image_url
    2) Расширенная: title + blocks (json array) -> если в database.py есть add_news_with_blocks, используем.
    blocks format example:
    [
        {"type":"text", "content":"Первый абзац"},
        {"type":"image", "content":"/uploads/.."},
        {"type":"video", "content":"https://..."}
    ]
    """
    try:
        # Если пришёл JSON и есть blocks — используем расширенную вставку (если поддерживается)
        if request.is_json and isinstance(request.json, dict) and 'blocks' in request.json:
            title = request.json.get('title', '')
            blocks = request.json.get('blocks', [])
            # если в database есть функция add_news_with_blocks - используем
            if hasattr(db_module, 'add_news_with_blocks'):
                news_id = db_module.add_news_with_blocks(title, blocks)
                cache_delete('news_list')
                return jsonify(success=True, news_id=news_id)
            else:
                # иначе пытаемся собрать текст из блоков в один большой текст и сохранить обычным add_news
                # (fallback)
                compiled_text_parts = []
                image_url = ''
                for b in blocks:
                    if isinstance(b, dict):
                        if b.get('type') == 'text':
                            compiled_text_parts.append(b.get('content',''))
                        elif b.get('type') == 'image' and not image_url:
                            image_url = b.get('content','')
                        elif b.get('type') == 'video' and not image_url:
                            # можно вставить ссылку в текст
                            compiled_text_parts.append(f"[Видео] {b.get('content','')}")
                compiled_text = "\n\n".join(compiled_text_parts)
                add_news(title, compiled_text, image_url)
                cache_delete('news_list')
                return jsonify(success=True)
        # Простая форма (form-data или json без blocks)
        title = ''
        text = ''
        image_url = ''
        if request.is_json:
            title = request.json.get('title', '')
            text = request.json.get('text', '')
            image_url = request.json.get('image_url', '')
        else:
            title = request.form.get('title', '')
            text = request.form.get('text', '')
        if 'image_file' in request.files and request.files['image_file'].filename != '':
            image_url = save_uploaded_file(request.files['image_file'], ALLOWED_IMAGE_EXTENSIONS) or image_url
        if not image_url and request.form.get('image_url'):
            image_url = request.form.get('image_url')
        add_news(title, text, image_url)
        cache_delete('news_list')
        return jsonify(success=True)
    except Exception as e:
        logger.exception(f"API add_news error: {e}")
        return jsonify(success=False, error=str(e))

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    # отдаём файл из папки uploads
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=False)

# --- API для реакций и комментариев ---
@app.route('/api/reaction', methods=['POST'])
def api_add_reaction():
    try:
        data = request.json if request.is_json else request.form
        item_type = data.get('item_type')
        item_id = data.get('item_id')
        user_id = data.get('user_id', 'anonymous')
        reaction = data.get('reaction')
        success = add_reaction(item_type, item_id, user_id, reaction)
        # можно обновить кэш для страницы конкретного типа
        cache_delete(f"{item_type}s_list" if item_type != 'news' else 'news_list')
        return jsonify(success=bool(success))
    except Exception as e:
        logger.exception(f"API add_reaction error: {e}")
        return jsonify(success=False, error=str(e))

@app.route('/api/comments', methods=['GET'])
def api_get_comments():
    try:
        item_type = request.args.get('type')
        item_id = request.args.get('id')
        comments = get_comments(item_type, int(item_id))
        # возвращаем в json-friendly виде
        return jsonify(comments=comments)
    except Exception as e:
        logger.exception(f"API get_comments error: {e}")
        return jsonify(comments=[], error=str(e))

@app.route('/api/comment', methods=['POST'])
def api_add_comment():
    try:
        data = request.json if request.is_json else request.form
        item_type = data.get('item_type')
        item_id = data.get('item_id')
        user_name = data.get('user_name', 'Гость')
        text = data.get('text', '')
        add_comment(item_type, item_id, user_name, text)
        cache_delete(f"{item_type}s_list" if item_type != 'news' else 'news_list')
        return jsonify(success=True)
    except Exception as e:
        logger.exception(f"API add_comment error: {e}")
        return jsonify(success=False, error=str(e))

# --- Admin routes ---
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

@app.route('/admin/content')
@admin_required
def admin_content():
    moments = get_all_moments()
    trailers = get_all_trailers()
    # Для новостей используем get_news_with_blocks, если есть, чтобы админ видел блоки
    try:
        if hasattr(db_module, 'get_news_with_blocks'):
            news = db_module.get_news_with_blocks()
        else:
            news = get_all_news()
    except Exception:
        news = get_all_news()
    return render_template('admin/content.html', moments=moments, trailers=trailers, news=news)

@app.route('/admin/delete/<content_type>/<int:content_id>')
@admin_required
def admin_delete(content_type, content_id):
    try:
        if content_type == 'moment':
            delete_moment(content_id)
            cache_delete('moments_list')
        elif content_type == 'trailer':
            delete_trailer(content_id)
            cache_delete('trailers_list')
        elif content_type == 'news':
            delete_news(content_id)
            cache_delete('news_list')
    except Exception as e:
        logger.exception(f"Admin delete error: {e}")
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

# --- Run bot + flask ---
def start_bot():
    try:
        updater.start_polling()
    except Exception as e:
        logger.exception(f"Failed to start telegram bot polling: {e}")
    try:
        updater.idle()
    except Exception:
        pass

if __name__ == '__main__':
    # Инициализация БД (если нужна)
    try:
        init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.warning(f"DB init failed (maybe already configured): {e}")

    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()

    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
