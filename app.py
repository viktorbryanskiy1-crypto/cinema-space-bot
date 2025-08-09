from flask import Flask, render_template, request
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, Update
from telegram.ext import Updater, CommandHandler
import os
import threading

# Получаем токен и URL из переменных окружения
TOKEN = os.environ.get('TELEGRAM_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://cinema-space-bot.onrender.com')

# Создаем Flask приложение
app = Flask(__name__)

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
    return render_template('moments.html')

# Вкладка: Трейлеры
@app.route('/trailers')
def trailers():
    return render_template('trailers.html')

# Вкладка: Новости
@app.route('/news')
def news():
    return render_template('news.html')

# Поиск
@app.route('/search')
def search():
    query = request.args.get('q', '')
    return render_template('search.html', query=query)

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
