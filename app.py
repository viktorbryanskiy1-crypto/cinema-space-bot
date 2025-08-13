# app.py
import os
import io
import threading
import logging
import uuid
import mimetypes
from datetime import datetime
from urllib.parse import urlparse
from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, session, send_from_directory, abort
)
from werkzeug.utils import secure_filename
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler
import psycopg2
import requests

# ====== Импорт из вашего database.py ======
# В database.py должны быть функции работы с PostgreSQL (а не SQLite).
# Мы используем их как "бизнес-логику" хранения контента/реакций/комментариев/ролей.
from database import (
    get_or_create_user, get_user_role,
    add_moment, add_trailer, add_news,
    get_all_moments, get_all_trailers, get_all_news,
    get_reactions_count, get_comments,
    add_reaction, add_comment,
    authenticate_admin, get_stats,
    delete_moment, delete_trailer, delete_news,
    get_access_settings, update_access_settings,
    init_db
)

# ====== Логирование ======
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("cinema-space")

# ====== Конфигурация окружения ======
TOKEN = os.environ.get('TELEGRAM_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://cinema-space-bot.onrender.com').strip()
if not TOKEN:
    logger.error("TELEGRAM_TOKEN не установлен!")
    raise SystemExit(1)

DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_NAME = os.environ.get('DB_NAME', 'cinema')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASS = os.environ.get('DB_PASS', 'postgres')

# ====== Flask ======
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'super-secret-key-change-me-please')

# Ограничения и директории для загрузок
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename: str, allowed_extensions: set) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

# ====== Telegram Bot ======
updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher

# Таблица для состояния кнопки в Telegram (двухсостояние)
def ensure_tg_state_table():
    try:
        conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS telegram_users (
                telegram_id BIGINT PRIMARY KEY,
                started BOOLEAN DEFAULT FALSE
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"Не удалось создать таблицу telegram_users: {e}")

ensure_tg_state_table()

# ====== Вспомогательные функции загрузки и "умного" сохранения по URL ======
def _unique_basename(filename: str) -> str:
    safe = secure_filename(filename) if filename else 'file'
    return f"{uuid.uuid4()}_{safe}"

def _guess_ext_from_mime(content_type: str, fallback: str = '') -> str:
    if not content_type:
        return fallback
    ext = mimetypes.guess_extension(content_type.split(';')[0].strip())
    if ext:
        return ext.lstrip('.')
    return fallback

def save_uploaded_file(file_storage, allowed_exts) -> str | None:
    """
    Сохраняет присланный файл в /uploads и возвращает web-путь '/uploads/<name>'.
    """
    if file_storage and allowed_file(file_storage.filename, allowed_exts):
        filename = _unique_basename(file_storage.filename)
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file_storage.save(path)
        return f"/uploads/{filename}"
    return None

STREAMABLE_HOSTS = ("youtube.com", "youtu.be", "vimeo.com", "t.me", "telegram.me", "telegram.org")

def _should_download_to_server(url: str) -> bool:
    """
    Решаем, имеет ли смысл скачивать на сервер:
    - НЕ скачиваем YouTube/Vimeo/Telegram (их надо встраивать)
    - Скачиваем прямые ссылки (CDN, файловые хостинги), если размер разумный
    """
    try:
        netloc = urlparse(url).netloc.lower()
        return url.lower().startswith("http") and not any(h in netloc for h in STREAMABLE_HOSTS)
    except Exception:
        return False

def _stream_download_to(path: str, response, max_bytes: int = 50 * 1024 * 1024):
    """
    Скачивает поток в файл с ограничением размера.
    """
    total = 0
    with open(path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 128):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("Файл превышает лимит 50MB")
            f.write(chunk)

def download_and_store(url: str, allowed_exts: set, prefer_ext: str = '') -> str | None:
    """
    Скачивает файл по прямому URL и кладёт в /uploads, возвращает web-путь.
    Для видео/изображений определяем расширение по content-type/URL.
    """
    try:
        with requests.get(url, stream=True, timeout=12) as r:
            r.raise_for_status()
            # Выясняем расширение
            content_type = r.headers.get("Content-Type", "")
            guess_ext = _guess_ext_from_mime(content_type, fallback=prefer_ext)
            # если в URL есть расширение и оно разрешено — используем его
            url_path = urlparse(url).path
            url_ext = os.path.splitext(url_path)[1].lstrip('.').lower()
            ext = url_ext if url_ext in allowed_exts else (guess_ext if guess_ext in allowed_exts else '')
            if not ext:
                # Если не распознали — пробуем mp4/png по типу
                if 'video' in content_type:
                    ext = 'mp4' if 'mp4' in ALLOWED_VIDEO_EXTENSIONS else list(ALLOWED_VIDEO_EXTENSIONS)[0]
                elif 'image' in content_type:
                    ext = 'png' if 'png' in ALLOWED_IMAGE_EXTENSIONS else list(ALLOWED_IMAGE_EXTENSIONS)[0]
                else:
                    # неизвестный тип — лучше отказаться
                    raise ValueError("Неподдерживаемый тип контента по URL")

            filename = _unique_basename(f"remote.{ext}")
            path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            _stream_download_to(path, r, max_bytes=50 * 1024 * 1024)
            return f"/uploads/{filename}"
    except Exception as e:
        logger.warning(f"Не удалось скачать по URL {url}: {e}")
        return None

# ====== Двухсостояние /start ======
def start(update, context):
    try:
        user = update.message.from_user
        telegram_id = str(user.id)

        # Регистрация пользователя в вашей БД (из database.py)
        get_or_create_user(
            telegram_id=telegram_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )

        # Проверяем состояние "started" в PostgreSQL
        started = True
        try:
            conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)
            cur = conn.cursor()
            cur.execute("SELECT started FROM telegram_users WHERE telegram_id=%s;", (telegram_id,))
            row = cur.fetchone()
            if row is None:
                cur.execute("INSERT INTO telegram_users (telegram_id, started) VALUES (%s, %s);", (telegram_id, False))
                conn.commit()
                started = False
            else:
                started = bool(row[0])
            cur.close()
            conn.close()
        except Exception as e:
            logger.error(f"Ошибка БД при /start: {e}")
            started = True  # по умолчанию показываем кнопку открытия

        if not started:
            # Первый раз: показываем кнопку "Начать"
            keyboard = [[InlineKeyboardButton("Начать", callback_data="start_app")]]
        else:
            # Уже запускал: сразу даём WebApp-кнопку
            keyboard = [[InlineKeyboardButton("🌌 КиноВселенная", web_app=WebAppInfo(url=f"{WEBHOOK_URL}?mode=fullscreen"))]]

        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(
            "🚀 Добро пожаловать в КиноВселенную!\n"
            "🎬 Моменты | 🎥 Трейлеры | 📰 Новости\n\n"
            "Нажмите кнопку ниже:",
            reply_markup=reply_markup
        )
        logger.info(f"/start от пользователя {telegram_id}")
    except Exception as e:
        logger.exception(f"Ошибка в обработке /start: {e}")

def button_callback(update, context):
    query = update.callback_query
    telegram_id = query.from_user.id

    if query.data == "start_app":
        # Меняем сообщение и даём WebApp-кнопку
        keyboard = [[InlineKeyboardButton("🌌 КиноВселенная", web_app=WebAppInfo(url=f"{WEBHOOK_URL}?mode=fullscreen"))]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            query.edit_message_text("Приложение готово! Нажмите кнопку ниже:", reply_markup=reply_markup)
        except Exception:
            # Если нельзя редактировать (старое сообщение) — просто ответим
            query.message.reply_text("Приложение готово! Нажмите кнопку ниже:", reply_markup=reply_markup)

        # Обновляем состояние в БД
        try:
            conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)
            cur = conn.cursor()
            cur.execute("UPDATE telegram_users SET started=TRUE WHERE telegram_id=%s;", (telegram_id,))
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            logger.error(f"Ошибка обновления started для {telegram_id}: {e}")

# ====== Добавление видео через команду (для админов/владельцев) ======
pending_video_data = {}

def add_video_command(update, context):
    user = update.message.from_user
    telegram_id = str(user.id)
    user_role = get_user_role(telegram_id)
    if user_role not in ['owner', 'admin']:
        update.message.reply_text("❌ У вас нет прав для добавления видео!")
        return

    text = update.message.text.strip()
    if not text.startswith('/add_video '):
        update.message.reply_text("❌ Формат: /add_video [moment|trailer|news] [Название]")
        return

    parts = text.split(' ', 2)
    if len(parts) < 3:
        update.message.reply_text("❌ Используйте формат: /add_video [тип] [название]")
        return

    content_type = parts[1].lower()
    title = parts[2]
    if content_type not in ['moment', 'trailer', 'news']:
        update.message.reply_text("❌ Тип: moment | trailer | news")
        return

    pending_video_data[telegram_id] = {
        'content_type': content_type,
        'title': title
    }

    update.message.reply_text(
        f"🎬 Добавление {content_type} «{title}».\n"
        f"Пришлите ссылку на видео (YouTube/Telegram/прямой URL)."
    )

def handle_pending_video_url(update, context):
    user = update.message.from_user
    telegram_id = str(user.id)
    if telegram_id not in pending_video_data:
        return

    video_url = (update.message.text or '').strip()
    if not video_url:
        update.message.reply_text("❌ Ссылка не может быть пустой. Попробуйте ещё раз.")
        return

    data = pending_video_data.pop(telegram_id)
    content_type = data['content_type']
    title = data['title']

    # Если это прямая ссылка (CDN/файл), попробуем скачать и хранить локально
    local_url = None
    if _should_download_to_server(video_url):
        local_url = download_and_store(video_url, ALLOWED_VIDEO_EXTENSIONS)

    final_url = local_url or video_url
    description = "Добавлено через Telegram"

    try:
        if content_type == 'moment':
            add_moment(title, description, final_url)
        elif content_type == 'trailer':
            add_trailer(title, description, final_url)
        elif content_type == 'news':
            add_news(title, description, final_url)  # тут видео_url трактуется как ссылка (редко для news)
        update.message.reply_text(f"✅ {content_type} «{title}» добавлен!")
    except Exception as e:
        logger.exception("Ошибка добавления через бота")
        update.message.reply_text(f"❌ Ошибка: {e}")

# Регистрируем хэндлеры
dp.add_handler(CommandHandler('start', start))
dp.add_handler(CallbackQueryHandler(button_callback))
dp.add_handler(CommandHandler('add_video', add_video_command))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_pending_video_url))

# ====== Telegram webhook endpoint (можно оставить, даже если используете polling) ======
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), updater.bot)
    updater.dispatcher.process_update(update)
    return 'ok'

# ====== Flask маршруты ======
@app.route('/')
def index():
    # Ваш index.html может выполнять Telegram.WebApp.expand() для полного экрана
    return render_template('index.html')

@app.route('/moments')
def moments():
    items = get_all_moments()
    enriched = []
    for m in items:
        reactions = get_reactions_count('moment', m[0])
        comments_count = len(get_comments('moment', m[0]))
        enriched.append({
            'id': m[0],
            'title': m[1],
            'description': m[2],
            'video_url': m[3],
            'created_at': m[4],
            'reactions': reactions,
            'comments_count': comments_count
        })
    return render_template('moments.html', moments=enriched)

@app.route('/trailers')
def trailers():
    items = get_all_trailers()
    enriched = []
    for t in items:
        reactions = get_reactions_count('trailer', t[0])
        comments_count = len(get_comments('trailer', t[0]))
        enriched.append({
            'id': t[0],
            'title': t[1],
            'description': t[2],
            'video_url': t[3],
            'created_at': t[4],
            'reactions': reactions,
            'comments_count': comments_count
        })
    return render_template('trailers.html', trailers=enriched)

@app.route('/news')
def news():
    items = get_all_news()
    enriched = []
    for n in items:
        reactions = get_reactions_count('news', n[0])
        comments_count = len(get_comments('news', n[0]))
        enriched.append({
            'id': n[0],
            'title': n[1],
            'text': n[2],
            'image_url': n[3],
            'created_at': n[4],
            'reactions': reactions,
            'comments_count': comments_count
        })
    return render_template('news.html', news=enriched)

@app.route('/search')
def search():
    query = request.args.get('q', '')
    # TODO: если нужно — реализуй поиск в database.py
    results = []
    return render_template('search.html', query=query, results=results)

# ====== API: добавление контента (файл / URL + опциональное скачивание прямых ссылок) ======
@app.route('/api/add_moment', methods=['POST'])
def api_add_moment():
    try:
        # 1) Приоритет — загруженный файл
        video_url = ''
        if 'video_file' in request.files and request.files['video_file'].filename:
            video_url = save_uploaded_file(request.files['video_file'], ALLOWED_VIDEO_EXTENSIONS) or ''

        # 2) Если файла нет — берем URL
        if not video_url:
            if request.is_json:
                video_url = (request.json or {}).get('video_url', '') or ''
                title = (request.json or {}).get('title', '') or ''
                description = (request.json or {}).get('description', '') or ''
            else:
                video_url = request.form.get('video_url', '') or ''
                title = request.form.get('title', '') or ''
                description = request.form.get('description', '') or ''
        else:
            # Файл есть, а текстовые поля могут прийти в form-data
            title = request.form.get('title', '') if request.form else ''
            description = request.form.get('description', '') if request.form else ''

        # 3) Если пришёл прямой URL (CDN) — пробуем скачать на сервер
        if not video_url.startswith('/uploads/') and _should_download_to_server(video_url):
            local = download_and_store(video_url, ALLOWED_VIDEO_EXTENSIONS)
            if local:
                video_url = local

        add_moment(title, description, video_url)
        return jsonify(success=True)
    except Exception as e:
        logger.exception("API add_moment error")
        return jsonify(success=False, error=str(e)), 400

@app.route('/api/add_trailer', methods=['POST'])
def api_add_trailer():
    try:
        video_url = ''
        if 'video_file' in request.files and request.files['video_file'].filename:
            video_url = save_uploaded_file(request.files['video_file'], ALLOWED_VIDEO_EXTENSIONS) or ''

        if not video_url:
            if request.is_json:
                video_url = (request.json or {}).get('video_url', '') or ''
                title = (request.json or {}).get('title', '') or ''
                description = (request.json or {}).get('description', '') or ''
            else:
                video_url = request.form.get('video_url', '') or ''
                title = request.form.get('title', '') or ''
                description = request.form.get('description', '') or ''
        else:
            title = request.form.get('title', '') if request.form else ''
            description = request.form.get('description', '') if request.form else ''

        if not video_url.startswith('/uploads/') and _should_download_to_server(video_url):
            local = download_and_store(video_url, ALLOWED_VIDEO_EXTENSIONS)
            if local:
                video_url = local

        add_trailer(title, description, video_url)
        return jsonify(success=True)
    except Exception as e:
        logger.exception("API add_trailer error")
        return jsonify(success=False, error=str(e)), 400

@app.route('/api/add_news', methods=['POST'])
def api_add_news():
    try:
        if request.is_json:
            title = (request.json or {}).get('title', '') or ''
            text = (request.json or {}).get('text', '') or ''
            image_url = (request.json or {}).get('image_url', '') or ''
        else:
            title = request.form.get('title', '') or ''
            text = request.form.get('text', '') or ''
            image_url = request.form.get('image_url', '') or ''

        # Файл изображения имеет приоритет
        if 'image_file' in request.files and request.files['image_file'].filename:
            image_url = save_uploaded_file(request.files['image_file'], ALLOWED_IMAGE_EXTENSIONS) or image_url

        # Если пришёл прямой URL (CDN) для картинки — пробуем скачать на сервер
        if image_url and not image_url.startswith('/uploads/') and _should_download_to_server(image_url):
            local = download_and_store(image_url, ALLOWED_IMAGE_EXTENSIONS)
            if local:
                image_url = local

        add_news(title, text, image_url)
        return jsonify(success=True)
    except Exception as e:
        logger.exception("API add_news error")
        return jsonify(success=False, error=str(e)), 400

# ====== Отдача загруженных файлов ======
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    safe = secure_filename(filename)
    full_path = os.path.join(app.config['UPLOAD_FOLDER'], safe)
    if not os.path.isfile(full_path):
        abort(404)
    return send_from_directory(app.config['UPLOAD_FOLDER'], safe, as_attachment=False)

# ====== Реакции и комментарии ======
@app.route('/api/reaction', methods=['POST'])
def api_add_reaction():
    try:
        data = request.get_json(force=True)
        success = add_reaction(
            data.get('item_type'),
            data.get('item_id'),
            data.get('user_id', 'anonymous'),
            data.get('reaction')
        )
        return jsonify(success=success)
    except Exception as e:
        logger.exception("API add_reaction error")
        return jsonify(success=False, error=str(e)), 400

@app.route('/api/comments', methods=['GET'])
def api_get_comments():
    try:
        item_type = request.args.get('type')
        item_id = int(request.args.get('id'))
        comments = get_comments(item_type, item_id)
        return jsonify(comments=comments)
    except Exception as e:
        logger.exception("API get_comments error")
        return jsonify(comments=[], error=str(e)), 400

@app.route('/api/comment', methods=['POST'])
def api_add_comment():
    try:
        data = request.get_json(force=True)
        add_comment(
            data.get('item_type'),
            data.get('item_id'),
            data.get('user_name', 'Гость'),
            data.get('text')
        )
        return jsonify(success=True)
    except Exception as e:
        logger.exception("API add_comment error")
        return jsonify(success=False, error=str(e)), 400

# ====== Админка ======
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
    return render_template(
        'admin/dashboard.html',
        moments_count=stats.get('moments', 0),
        trailers_count=stats.get('trailers', 0),
        news_count=stats.get('news', 0),
        comments_count=stats.get('comments', 0)
    )

@app.route('/admin/content')
@admin_required
def admin_content():
    moments = get_all_moments()
    trailers = get_all_trailers()
    news = get_all_news()
    return render_template('admin/content.html', moments=moments, trailers=trailers, news=news)

@app.route('/admin/delete/<content_type>/<int:content_id>')
@admin_required
def admin_delete(content_type, content_id):
    if content_type == 'moment':
        delete_moment(content_id)
    elif content_type == 'trailer':
        delete_trailer(content_id)
    elif content_type == 'news':
        delete_news(content_id)
    return redirect(url_for('admin_content'))

@app.route('/admin/access')
@admin_required
def admin_access_settings():
    moment_roles = get_access_settings('moment')
    trailer_roles = get_access_settings('trailer')
    news_roles = get_access_settings('news')
    logger.debug(f"Access settings -> moments: {moment_roles}, trailers: {trailer_roles}, news: {news_roles}")
    return render_template(
        'admin/access/settings.html',
        moment_roles=moment_roles,
        trailer_roles=trailer_roles,
        news_roles=news_roles
    )

@app.route('/admin/access/update/<content_type>', methods=['POST'])
@admin_required
def admin_update_access(content_type):
    roles = request.form.getlist('roles')
    update_access_settings(content_type, roles)
    logger.info(f"Updated access roles for {content_type}: {roles}")
    return redirect(url_for('admin_access_settings'))

# ====== Запуск бота и приложения ======
def start_bot():
    logger.info("Запуск Telegram бота (polling)...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    # 1) Инициализация вашей основной БД (контент/реакции/комменты/роли)
    try:
        init_db()
        logger.info("✅ База данных (контент) инициализирована.")
        print("✅ База данных (контент) инициализирована.")
    except Exception as e:
        logger.error(f"❌ Ошибка init_db(): {e}")
        print(f"❌ Ошибка init_db(): {e}")

    # 2) Инициализация таблицы telegram_users для состояния /start
    ensure_tg_state_table()

    # 3) Запуск бота в отдельном потоке
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()

    # 4) Flask
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
