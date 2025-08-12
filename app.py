from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_from_directory, flash
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import os
import threading
import json
from database import *
from werkzeug.utils import secure_filename
import uuid

# Получаем токен и URL из переменных окружения (если есть)
TOKEN = os.environ.get('TELEGRAM_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://cinema-space-bot.onrender.com')

app = Flask(__name__)
# Задай реальный секретный ключ в production через переменные окружения
app.secret_key = os.environ.get('FLASK_SECRET', 'change-me-to-random-secret')

# Конфигурация загрузок
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Разрешённые расширения
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

# --- TELEGRAM BOT (если у тебя есть TOKEN) ---
updater = None
if TOKEN:
    try:
        updater = Updater(TOKEN, use_context=True)
        dp = updater.dispatcher
    except Exception as e:
        print("Не удалось инициализировать Telegram Updater:", e)
        updater = None

def start(update, context):
    user = update.message.from_user
    telegram_id = str(user.id)
    # Сохраняем или обновляем инфу о пользователе
    try:
        get_or_create_user(
            telegram_id=telegram_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
    except Exception as e:
        print("Ошибка get_or_create_user:", e)

    keyboard = [[
        InlineKeyboardButton("🌌 КиноВселенная", web_app=WebAppInfo(url=WEBHOOK_URL))
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(
        "🚀 Добро пожаловать в КиноВселенная!\n"
        "Нажми кнопку для входа в космическое приложение",
        reply_markup=reply_markup
    )

def add_video_command(update, context):
    user = update.message.from_user
    telegram_id = str(user.id)
    user_role = get_user_role(telegram_id)
    if user_role not in ['owner', 'admin']:
        update.message.reply_text("❌ У вас нет прав для добавления видео!")
        return
    update.message.reply_text("Используй формат /add_video ... (см. инструкцию)")

def add_video_handler(update, context):
    # обрабатывает сообщения с командой /add_video (как в твоём коде)
    user = update.message.from_user
    telegram_id = str(user.id)
    user_role = get_user_role(telegram_id)
    if user_role not in ['owner', 'admin']:
        update.message.reply_text("❌ У вас нет прав для добавления видео!")
        return
    text = update.message.text or ""
    if not text.startswith('/add_video '):
        update.message.reply_text("❌ Неверный формат команды! Используйте: /add_video [тип] [название]")
        return
    lines = text.split('\n')
    if len(lines) < 2:
        update.message.reply_text("❌ Неверный формат команды! Введите название и ссылку на видео.")
        return
    command_line = lines[0]
    video_url = lines[1].strip()
    parts = command_line.split(' ', 3)
    if len(parts) < 3:
        update.message.reply_text("❌ Неверный формат команды! Используйте: /add_video [тип] [название]")
        return
    content_type = parts[1]
    title = ' '.join(parts[2:])
    if content_type not in ['moment', 'trailer', 'news']:
        update.message.reply_text("❌ Неверный тип контента! Доступные типы: moment, trailer, news")
        return
    try:
        if content_type == 'moment':
            add_moment(title, "Добавлено через Telegram", video_url)
        elif content_type == 'trailer':
            add_trailer(title, "Добавлено через Telegram", video_url)
        elif content_type == 'news':
            add_news(title, "Добавлено через Telegram", video_url)
        update.message.reply_text(f"✅ {content_type} '{title}' успешно добавлен!")
    except Exception as e:
        update.message.reply_text(f"❌ Ошибка: {e}")

# Подключаем хэндлеры, если бот проинициализирован
if updater:
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("add_video", add_video_command))
    dp.add_handler(MessageHandler(Filters.text & Filters.regex(r'^/add_video '), add_video_handler))

# --- Flask маршруты (вкладки UI) ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/moments')
def moments():
    moments_data = get_all_moments()
    moments_with_reactions = []
    for m in moments_data:
        reactions = get_reactions_count('moment', m[0])
        comments_count = len(get_comments('moment', m[0]))
        moments_with_reactions.append({
            'id': m[0],
            'title': m[1],
            'description': m[2],
            'video_url': m[3],
            'created_at': m[4],
            'reactions': reactions,
            'comments_count': comments_count
        })
    return render_template('moments.html', moments=moments_with_reactions)

@app.route('/trailers')
def trailers():
    trailers_data = get_all_trailers()
    trailers_with_reactions = []
    for t in trailers_data:
        reactions = get_reactions_count('trailer', t[0])
        comments_count = len(get_comments('trailer', t[0]))
        trailers_with_reactions.append({
            'id': t[0],
            'title': t[1],
            'description': t[2],
            'video_url': t[3],
            'created_at': t[4],
            'reactions': reactions,
            'comments_count': comments_count
        })
    return render_template('trailers.html', trailers=trailers_with_reactions)

@app.route('/news')
def news():
    news_data = get_all_news()
    news_with_reactions = []
    for n in news_data:
        reactions = get_reactions_count('news', n[0])
        comments_count = len(get_comments('news', n[0]))
        news_with_reactions.append({
            'id': n[0],
            'title': n[1],
            'text': n[2],
            'image_url': n[3],
            'created_at': n[4],
            'reactions': reactions,
            'comments_count': comments_count
        })
    return render_template('news.html', news=news_with_reactions)

@app.route('/search')
def search():
    query = request.args.get('q', '')
    # простая заглушка — позже можно сделать полнотекстовый поиск
    return render_template('search.html', query=query, results=[])

# --- API для добавления контента (работает с формами/загрузками) ---
@app.route('/api/add_moment', methods=['POST'])
def api_add_moment():
    try:
        video_url = ''
        if 'video_file' in request.files:
            file = request.files['video_file']
            if file and file.filename != '' and allowed_file(file.filename, ALLOWED_VIDEO_EXTENSIONS):
                filename = secure_filename(file.filename)
                unique_filename = str(uuid.uuid4()) + '_' + filename
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(filepath)
                video_url = f"/uploads/{unique_filename}"
        else:
            data = request.get_json(silent=True) or {}
            video_url = data.get('video_url', '')

        data = request.form if request.form else (request.get_json(silent=True) or {})
        add_moment(data.get('title', ''), data.get('description', ''), video_url)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/add_trailer', methods=['POST'])
def api_add_trailer():
    try:
        video_url = ''
        if 'video_file' in request.files:
            file = request.files['video_file']
            if file and file.filename != '' and allowed_file(file.filename, ALLOWED_VIDEO_EXTENSIONS):
                filename = secure_filename(file.filename)
                unique_filename = str(uuid.uuid4()) + '_' + filename
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(filepath)
                video_url = f"/uploads/{unique_filename}"
        else:
            data = request.get_json(silent=True) or {}
            video_url = data.get('video_url', '')

        data = request.form if request.form else (request.get_json(silent=True) or {})
        add_trailer(data.get('title', ''), data.get('description', ''), video_url)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/add_news', methods=['POST'])
def api_add_news():
    try:
        title = request.form.get('title', '')
        text = request.form.get('text', '')
        image_url = ''
        if 'image_file' in request.files:
            file = request.files['image_file']
            if file and file.filename != '' and allowed_file(file.filename, ALLOWED_IMAGE_EXTENSIONS):
                filename = secure_filename(file.filename)
                unique_filename = str(uuid.uuid4()) + '_' + filename
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(filepath)
                image_url = f"/uploads/{unique_filename}"
        if not image_url and 'image_url' in request.form:
            image_url = request.form['image_url']
        add_news(title, text, image_url)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# отдача загруженных файлов
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- reactions / comments API ---
@app.route('/api/reaction', methods=['POST'])
def api_add_reaction():
    data = request.json or {}
    success = add_reaction(
        data.get('item_type'),
        data.get('item_id'),
        data.get('user_id', 'anonymous'),
        data.get('reaction')
    )
    return jsonify({"success": success})

@app.route('/api/comments', methods=['GET'])
def api_get_comments():
    item_type = request.args.get('type')
    item_id = request.args.get('id')
    comments = get_comments(item_type, int(item_id))
    return jsonify({"comments": comments})

@app.route('/api/comment', methods=['POST'])
def api_add_comment():
    data = request.json or {}
    add_comment(
        data.get('item_type'),
        data.get('item_id'),
        data.get('user_name', 'Гость'),
        data.get('text', '')
    )
    return jsonify({"success": True})

# --- Admin auth + admin pages ---
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if authenticate_admin(username, password):
            session['admin'] = username
            flash('Успешный вход', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin/login.html', error='Неверный логин или пароль')
    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))

@app.route('/admin')
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    stats = get_stats()
    return render_template('admin/dashboard.html',
                           moments_count=stats['moments'],
                           trailers_count=stats['trailers'],
                           news_count=stats['news'],
                           comments_count=stats['comments'])

@app.route('/admin/content')
def admin_content():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    moments = get_all_moments()
    trailers = get_all_trailers()
    news = get_all_news()
    return render_template('admin/content.html', moments=moments, trailers=trailers, news=news)

@app.route('/admin/delete/<content_type>/<int:content_id>')
def admin_delete(content_type, content_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    if content_type == 'moment':
        delete_moment(content_id)
    elif content_type == 'trailer':
        delete_trailer(content_id)
    elif content_type == 'news':
        delete_news(content_id)
    return redirect(url_for('admin_content'))

# --- Access settings (исправлено) ---
@app.route('/admin/access')
def admin_access_settings():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    # Получаем роли из базы и передаём в шаблон
    moment_roles = get_access_settings('moment')
    trailer_roles = get_access_settings('trailer')
    news_roles = get_access_settings('news')
    return render_template('admin/access/settings.html',
                           moment_roles=moment_roles,
                           trailer_roles=trailer_roles,
                           news_roles=news_roles)

@app.route('/admin/access/update/<content_type>', methods=['POST'])
def admin_update_access(content_type):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    roles = request.form.getlist('roles')  # обязательно getlist для множественного выбора
    print(f"!!! ADMIN_UPDATE_ACCESS called for {content_type}, roles={roles}")
    success = update_access_settings(content_type, roles)
    if success:
        flash('Настройки доступа сохранены', 'success')
    else:
        flash('Ошибка при сохранении настроек', 'error')
    return redirect(url_for('admin_access_settings'))

# --- Telegram webhook starter (опционально) ---
def start_bot():
    if not updater:
        print("Telegram token не настроен — бот не будет запущен.")
        return
    try:
        WEBHOOK_URL_FULL = f"{WEBHOOK_URL}/{TOKEN}"
        updater.bot.set_webhook(url=WEBHOOK_URL_FULL)
        print("Webhook установлен:", WEBHOOK_URL_FULL)
    except Exception as e:
        print("Ошибка установки webhook (можно игнорировать если используешь polling):", e)
    updater.start_polling()

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    if not updater:
        return 'no token'
    update = Update.de_json(request.get_json(force=True), updater.bot)
    updater.dispatcher.process_update(update)
    return 'ok'

# --- Run ---
if __name__ == '__main__':
    # Запускаем бот в отдельном потоке (если есть токен)
    if updater:
        bot_thread = threading.Thread(target=start_bot, daemon=True)
        bot_thread.start()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=True)
