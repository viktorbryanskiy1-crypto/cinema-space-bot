import sqlite3
import os
from datetime import datetime
import bcrypt
import json

def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    
    # Таблица для моментов из кино
    c.execute('''CREATE TABLE IF NOT EXISTS moments
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT NOT NULL,
                  description TEXT,
                  video_url TEXT NOT NULL,
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # Таблица для трейлеров
    c.execute('''CREATE TABLE IF NOT EXISTS trailers
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT NOT NULL,
                  description TEXT,
                  video_url TEXT NOT NULL,
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # Таблица для новостей
    c.execute('''CREATE TABLE IF NOT EXISTS news
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT NOT NULL,
                  text TEXT NOT NULL,
                  image_url TEXT,
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # Таблица для комментариев
    c.execute('''CREATE TABLE IF NOT EXISTS comments
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  item_type TEXT NOT NULL, -- 'moment', 'trailer', 'news'
                  item_id INTEGER NOT NULL,
                  user_name TEXT NOT NULL,
                  text TEXT NOT NULL,
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # Таблица для реакций
    c.execute('''CREATE TABLE IF NOT EXISTS reactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  item_type TEXT NOT NULL,
                  item_id INTEGER NOT NULL,
                  user_id TEXT NOT NULL,
                  reaction TEXT NOT NULL,
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(item_type, item_id, user_id, reaction))''')
    
    # Таблица для администраторов
    c.execute('''CREATE TABLE IF NOT EXISTS admins
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password_hash TEXT NOT NULL,
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # Таблица для пользователей Telegram
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  telegram_id TEXT UNIQUE NOT NULL,
                  username TEXT,
                  first_name TEXT,
                  last_name TEXT,
                  role TEXT DEFAULT 'user', -- 'owner', 'admin', 'user', 'guest'
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # Таблица для настроек доступа
    c.execute('''CREATE TABLE IF NOT EXISTS access_settings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  content_type TEXT UNIQUE NOT NULL, -- 'moment', 'trailer', 'news'
                  allowed_roles TEXT NOT NULL, -- JSON строка с разрешенными ролями
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # Таблица для хранения ссылок на Telegram
    c.execute('''CREATE TABLE IF NOT EXISTS telegram_links
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  content_type TEXT NOT NULL, -- 'moment', 'trailer'
                  content_id INTEGER NOT NULL, -- ID из соответствующей таблицы (moments, trailers)
                  telegram_channel TEXT NOT NULL,
                  telegram_message_id TEXT NOT NULL,
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(content_type, content_id))''')
    
    # Создаем админа по умолчанию (admin/admin)
    try:
        password_hash = bcrypt.hashpw('admin'.encode('utf-8'), bcrypt.gensalt())
        c.execute("INSERT INTO admins (username, password_hash) VALUES (?, ?)",
                 ('admin', password_hash))
    except sqlite3.IntegrityError:
        pass  # Админ уже существует
    
    # Создаем владельца (тебя) - замени 'YOUR_TELEGRAM_ID' на свой ID
    try:
        c.execute("INSERT INTO users (telegram_id, username, first_name, last_name, role) VALUES (?, ?, ?, ?, ?)",
                 ('YOUR_TELEGRAM_ID', 'owner', 'Owner', 'User', 'owner'))
    except sqlite3.IntegrityError:
        pass  # Владелец уже существует
    
    # Создаем настройки доступа по умолчанию
    try:
        c.execute("INSERT INTO access_settings (content_type, allowed_roles) VALUES (?, ?)",
                 ('moment', '["owner"]'))  # Только владелец
        c.execute("INSERT INTO access_settings (content_type, allowed_roles) VALUES (?, ?)",
                 ('trailer', '["owner", "admin"]'))  # Владелец и админы
        c.execute("INSERT INTO access_settings (content_type, allowed_roles) VALUES (?, ?)",
                 ('news', '["owner", "admin", "user"]'))  # Все авторизованные
    except sqlite3.IntegrityError:
        pass  # Настройки уже существуют
    
    conn.commit()
    conn.close()

def get_all_moments():
    """Получить все моменты из кино"""
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    c.execute("SELECT * FROM moments ORDER BY created_at DESC")
    moments = c.fetchall()
    conn.close()
    return moments

def get_all_trailers():
    """Получить все трейлеры"""
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    c.execute("SELECT * FROM trailers ORDER BY created_at DESC")
    trailers = c.fetchall()
    conn.close()
    return trailers

def get_all_news():
    """Получить все новости"""
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    c.execute("SELECT * FROM news ORDER BY created_at DESC")
    news = c.fetchall()
    conn.close()
    return news

def add_moment(title, description, video_url):
    """Добавить момент из кино"""
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    c.execute("INSERT INTO moments (title, description, video_url) VALUES (?, ?, ?)",
              (title, description, video_url))
    conn.commit()
    conn.close()

def add_trailer(title, description, video_url):
    """Добавить трейлер"""
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    c.execute("INSERT INTO trailers (title, description, video_url) VALUES (?, ?, ?)",
              (title, description, video_url))
    conn.commit()
    conn.close()

def add_news(title, text, image_url):
    """Добавить новость"""
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    c.execute("INSERT INTO news (title, text, image_url) VALUES (?, ?, ?)",
              (title, text, image_url))
    conn.commit()
    conn.close()

def delete_moment(moment_id):
    """Удалить момент из кино"""
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    c.execute("DELETE FROM moments WHERE id = ?", (moment_id,))
    c.execute("DELETE FROM comments WHERE item_type = 'moment' AND item_id = ?", (moment_id,))
    c.execute("DELETE FROM reactions WHERE item_type = 'moment' AND item_id = ?", (moment_id,))
    conn.commit()
    conn.close()

def delete_trailer(trailer_id):
    """Удалить трейлер"""
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    c.execute("DELETE FROM trailers WHERE id = ?", (trailer_id,))
    c.execute("DELETE FROM comments WHERE item_type = 'trailer' AND item_id = ?", (trailer_id,))
    c.execute("DELETE FROM reactions WHERE item_type = 'trailer' AND item_id = ?", (trailer_id,))
    conn.commit()
    conn.close()

def delete_news(news_id):
    """Удалить новость"""
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    c.execute("DELETE FROM news WHERE id = ?", (news_id,))
    c.execute("DELETE FROM comments WHERE item_type = 'news' AND item_id = ?", (news_id,))
    c.execute("DELETE FROM reactions WHERE item_type = 'news' AND item_id = ?", (news_id,))
    conn.commit()
    conn.close()

def get_reactions_count(item_type, item_id):
    """Получить количество реакций для элемента"""
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    c.execute("""SELECT reaction, COUNT(*) 
                 FROM reactions 
                 WHERE item_type = ? AND item_id = ? 
                 GROUP BY reaction""", (item_type, item_id))
    results = c.fetchall()
    conn.close()
    
    reactions = {'like': 0, 'dislike': 0, 'star': 0, 'fire': 0}
    for reaction, count in results:
        reactions[reaction] = count
    
    return reactions

def add_reaction(item_type, item_id, user_id, reaction):
    """Добавить реакцию"""
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    
    # Удаляем существующую реакцию того же типа от этого пользователя
    c.execute("""DELETE FROM reactions 
                 WHERE item_type = ? AND item_id = ? AND user_id = ? AND reaction = ?""",
              (item_type, item_id, user_id, reaction))
    
    # Добавляем новую реакцию
    try:
        c.execute("""INSERT INTO reactions (item_type, item_id, user_id, reaction) 
                     VALUES (?, ?, ?, ?)""",
                  (item_type, item_id, user_id, reaction))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    
    conn.close()
    return success

def get_comments(item_type, item_id):
    """Получить комментарии для элемента"""
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    c.execute("""SELECT user_name, text, created_at 
                 FROM comments 
                 WHERE item_type = ? AND item_id = ? 
                 ORDER BY created_at DESC""", (item_type, item_id))
    comments = c.fetchall()
    conn.close()
    return comments

def add_comment(item_type, item_id, user_name, text):
    """Добавить комментарий"""
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    c.execute("""INSERT INTO comments (item_type, item_id, user_name, text) 
                 VALUES (?, ?, ?, ?)""",
              (item_type, item_id, user_name, text))
    conn.commit()
    conn.close()

def authenticate_admin(username, password):
    """Проверка авторизации администратора"""
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    c.execute("SELECT password_hash FROM admins WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    
    if result:
        stored_hash = result[0]
        return bcrypt.checkpw(password.encode('utf-8'), stored_hash)
    return False

def get_stats():
    """Получить статистику"""
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM moments")
    moments_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM trailers")
    trailers_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM news")
    news_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM comments")
    comments_count = c.fetchone()[0]
    
    conn.close()
    
    return {
        'moments': moments_count,
        'trailers': trailers_count,
        'news': news_count,
        'comments': comments_count
    }

def get_or_create_user(telegram_id, username=None, first_name=None, last_name=None):
    """Получить или создать пользователя по Telegram ID"""
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    
    # Проверяем, существует ли пользователь
    c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    user = c.fetchone()
    
    if user:
        # Обновляем информацию о пользователе
        c.execute("""UPDATE users 
                     SET username = ?, first_name = ?, last_name = ? 
                     WHERE telegram_id = ?""",
                  (username, first_name, last_name, telegram_id))
    else:
        # Создаем нового пользователя с ролью 'user' по умолчанию
        c.execute("""INSERT INTO users (telegram_id, username, first_name, last_name, role) 
                     VALUES (?, ?, ?, ?, ?)""",
                  (telegram_id, username, first_name, last_name, 'user'))
        # Получаем созданного пользователя
        c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        user = c.fetchone()
    
    conn.commit()
    conn.close()
    return user

def get_user_by_telegram_id(telegram_id):
    """Получить пользователя по Telegram ID"""
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    user = c.fetchone()
    conn.close()
    return user

def get_user_role(telegram_id):
    """Получить роль пользователя по Telegram ID"""
    user = get_user_by_telegram_id(telegram_id)
    if user:
        return user[5]  # role column
    return 'guest'  # По умолчанию гость

def get_access_settings(content_type):
    """Получить настройки доступа для типа контента"""
    print(f"!!! DB: get_access_settings called with content_type={content_type} !!!")
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    c.execute("SELECT allowed_roles FROM access_settings WHERE content_type = ?", (content_type,))
    result = c.fetchone()
    conn.close()
    print(f"!!! DB: get_access_settings query result={result} !!!")
    
    if result:
        try:
            roles_list = json.loads(result[0])
            print(f"!!! DB: get_access_settings returning parsed list: {roles_list} !!!")
            return roles_list
        except json.JSONDecodeError:
            print("!!! DB: get_access_settings JSON decode error, returning default ['owner'] !!!")
            return ['owner']
    print("!!! DB: get_access_settings returning default ['owner'] !!!")
    return ['owner']  # По умолчанию только владелец

def can_user_add_content(telegram_id, content_type):
    """Проверить, может ли пользователь добавлять контент определенного типа"""
    user_role = get_user_role(telegram_id)
    allowed_roles = get_access_settings(content_type)
    
    # Владелец может всё
    if user_role == 'owner':
        return True
    
    # Проверяем, есть ли роль пользователя в списке разрешенных
    return user_role in allowed_roles

def get_all_users():
    """Получить всех пользователей"""
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users ORDER BY created_at DESC")
    users = c.fetchall()
    conn.close()
    return users

def update_user_role(telegram_id, new_role):
    """Обновить роль пользователя"""
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    c.execute("UPDATE users SET role = ? WHERE telegram_id = ?", (new_role, telegram_id))
    conn.commit()
    conn.close()

def update_access_settings(content_type, allowed_roles):
    """Обновить настройки доступа"""
    print(f"!!! DB: update_access_settings called with content_type={content_type}, allowed_roles={allowed_roles} !!!")
    conn = sqlite3.connect('cinema.db')
    c = conn.cursor()
    try:
        # Преобразуем список ролей в JSON строку
        roles_json = json.dumps(allowed_roles)
        print(f"!!! DB: Trying to update with roles_json={roles_json} !!!")
        
        # Обновляем настройки доступа
        c.execute("UPDATE access_settings SET allowed_roles = ? WHERE content_type = ?", 
                  (roles_json, content_type))
        print(f"!!! DB: UPDATE executed, rowcount={c.rowcount} !!!")
        conn.commit()
        print("!!! DB: Commit successful !!!")
        success = True
    except Exception as e:
        print(f"!!! DB: Error during UPDATE/commit: {e} !!!")
        success = False
    finally:
        conn.close()
        print("!!! DB: Connection closed !!!")
    return success

# Инициализация базы данных при импорте
init_db()
