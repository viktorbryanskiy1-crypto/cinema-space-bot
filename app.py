from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, Update
from telegram.ext import Updater, CommandHandler
import os
import threading
import json
from database import *
from werkzeug.utils import secure_filename
import uuid

# Получаем токен и URL из переменных окружения
TOKEN = os.environ.get('TELEGRAM_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://cinema-space-bot.onrender.com')

# Создаем Flask приложение
app = Flask(__name__)

# Конфигурация для загрузки файлов
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # Максимальный размер файла 50MB
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Поддерживаемые форматы файлов
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

# Инициализируем бота
updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher

def start(update, context):
    keyboard = [[
        InlineKeyboardButton(
            "🌌 КиноВселенная", 
            web_app=WebAppInfo(url=WEBHOOK_URL)
        )
    ]]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(
        "🚀 Добро пожаловать в КиноВселенная!\n"
        "✨ Исследуй космос кино\n"
        "🎬 Лучшие моменты из фильмов\n"
        "🎥 Свежие трейлеры\n"
        "📰 Горячие новости\n\n"
        "Нажми кнопку для входа в космическое приложение",
        reply_markup=reply_markup
    )

# Регистрируем обработчики команд
dp.add_handler(CommandHandler("start", start))

# Обработчик webhook
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), updater.bot)
    updater.dispatcher.process_update(update)
    return 'ok'

# Главная страница
@app.route('/')
def index():
    return render_template('index.html')

# Вкладка: Моменты из кино
@app.route('/moments')
def moments():
    moments_data = get_all_moments()
    # Добавляем реакции для каждого элемента
    moments_with_reactions = []
    for moment in moments_data:
        reactions = get_reactions_count('moment', moment[0])
        comments_count = len(get_comments('moment', moment[0]))
        moments_with_reactions.append({
            'id': moment[0],
            'title': moment[1],
            'description': moment[2],
            'video_url': moment[3],
            'created_at': moment[4],
            'reactions': reactions,
            'comments_count': comments_count
        })
    return render_template('moments.html', moments=moments_with_reactions)

# Вкладка: Трейлеры
@app.route('/trailers')
def trailers():
    trailers_data = get_all_trailers()
    # Добавляем реакции для каждого элемента
    trailers_with_reactions = []
    for trailer in trailers_data:
        reactions = get_reactions_count('trailer', trailer[0])
        comments_count = len(get_comments('trailer', trailer[0]))
        trailers_with_reactions.append({
            'id': trailer[0],
            'title': trailer[1],
            'description': trailer[2],
            'video_url': trailer[3],
            'created_at': trailer[4],
            'reactions': reactions,
            'comments_count': comments_count
        })
    return render_template('trailers.html', trailers=trailers_with_reactions)

# Вкладка: Новости
@app.route('/news')
def news():
    news_data = get_all_news()
    # Добавляем реакции для каждого элемента
    news_with_reactions = []
    for news_item in news_data:
        reactions = get_reactions_count('news', news_item[0])
        comments_count = len(get_comments('news', news_item[0]))
        news_with_reactions.append({
            'id': news_item[0],
            'title': news_item[1],
            'text': news_item[2],
            'image_url': news_item[3],
            'created_at': news_item[4],
            'reactions': reactions,
            'comments_count': comments_count
        })
    return render_template('news.html', news=news_with_reactions)

# Поиск
@app.route('/search')
def search():
    query = request.args.get('q', '')
    if query:
        # Здесь будет логика поиска
        return render_template('search.html', query=query, results=[])
    return render_template('search.html', query='', results=[])

# API endpoints для добавления контента
@app.route('/api/add_moment', methods=['POST'])
def api_add_moment():
    try:
        data = request.get_json()
        # Проверяем, есть ли видео файл
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
            video_url = data.get('video_url', '')
        
        add_moment(data['title'], data['description'], video_url)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/add_trailer', methods=['POST'])
def api_add_trailer():
    try:
        data = request.get_json()
        # Проверяем, есть ли видео файл
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
            video_url = data.get('video_url', '')
        
        add_trailer(data['title'], data['description'], video_url)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/add_news', methods=['POST'])
def api_add_news():
    try:
        # Получаем текстовые данные
        title = request.form.get('title', '')
        text = request.form.get('text', '')
        image_url = ''
        
        # Проверяем, есть ли файл изображения
        if 'image_file' in request.files:
            file = request.files['image_file']
            if file and file.filename != '' and allowed_file(file.filename, ALLOWED_IMAGE_EXTENSIONS):
                filename = secure_filename(file.filename)
                unique_filename = str(uuid.uuid4()) + '_' + filename
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(filepath)
                image_url = f"/uploads/{unique_filename}"
        
        # Если нет файла, проверяем URL изображения
        if not image_url and 'image_url' in request.form:
            image_url = request.form['image_url']
        
        # Добавляем новость в базу данных
        add_news(title, text, image_url)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# Endpoint для отдачи загруженных файлов
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# API endpoints для реакций и комментариев
@app.route('/api/reaction', methods=['POST'])
def api_add_reaction():
    data = request.json
    success = add_reaction(
        data['item_type'], 
        data['item_id'], 
        data.get('user_id', 'anonymous'), 
        data['reaction']
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
    data = request.json
    add_comment(
        data['item_type'],
        data['item_id'],
        data.get('user_name', 'Гость'),
        data['text']
    )
    return jsonify({"success": True})

# Админ-панель
@app.route('/admin')
def admin():
    # Здесь будет логика админ-панели
    return "<h1>Админ-панель</h1><p>Скоро здесь появится управление контентом</p>"

# Запуск бота в отдельном потоке
def start_bot():
    updater.start_polling()

if __name__ == '__main__':
    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=start_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Запускаем Flask сервер
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
