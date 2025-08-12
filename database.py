# database.py
import psycopg2
import os
from datetime import datetime
import bcrypt
import json
from psycopg2.extras import RealDictCursor

def get_db_connection():
    """Получить подключение к базе данных PostgreSQL"""
    # Получаем строку подключения из переменной окружения, установленной Render
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise Exception("DATABASE_URL environment variable is not set")
    
    # Psycopg2 может напрямую использовать DATABASE_URL
    conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
    return conn

def init_db():
    """Инициализация базы данных PostgreSQL"""
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        # Таблица для моментов из кино
        c.execute("""
            CREATE TABLE IF NOT EXISTS moments (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                video_url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица для трейлеров
        c.execute("""
            CREATE TABLE IF NOT EXISTS trailers (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                video_url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица для новостей
        c.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                text TEXT NOT NULL,
                image_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица для комментариев
        c.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id SERIAL PRIMARY KEY,
                item_type TEXT NOT NULL, -- 'moment', 'trailer', 'news'
                item_id INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица для реакций
        c.execute("""
            CREATE TABLE IF NOT EXISTS reactions (
                id SERIAL PRIMARY KEY,
                item_type TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                reaction TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(item_type, item_id, user_id, reaction)
            )
        """)
        
        # Таблица для администраторов
        c.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash BYTEA NOT NULL, -- BYTEA для хранения бинарных данных (хеш bcrypt)
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица для пользователей Telegram
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id TEXT UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                role TEXT DEFAULT 'user', -- 'owner', 'admin', 'user', 'guest'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица для настроек доступа
        c.execute("""
            CREATE TABLE IF NOT EXISTS access_settings (
                id SERIAL PRIMARY KEY,
                content_type TEXT UNIQUE NOT NULL, -- 'moment', 'trailer', 'news'
                allowed_roles TEXT NOT NULL, -- JSON строка с разрешенными ролями
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Создаем админа по умолчанию (admin/admin)
        # Используем ON CONFLICT для предотвращения дубликатов
        password_hash = bcrypt.hashpw('admin'.encode('utf-8'), bcrypt.gensalt())
        c.execute("""
            INSERT INTO admins (username, password_hash) 
            VALUES (%s, %s)
            ON CONFLICT (username) DO NOTHING
        """, ('admin', password_hash))
        
        # Создаем владельца (тебя) - с вашим реальным Telegram ID
        c.execute("""
            INSERT INTO users (telegram_id, username, first_name, last_name, role) 
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (telegram_id) DO NOTHING
        """, ('993856446', 'owner_user', 'App', 'Owner', 'owner'))
        
        # Создаем настройки доступа по умолчанию
        # Используем ON CONFLICT для предотвращения дубликатов
        c.execute("""
            INSERT INTO access_settings (content_type, allowed_roles) 
            VALUES (%s, %s)
            ON CONFLICT (content_type) DO NOTHING
        """, ('moment', '["owner"]'))  # Только владелец
        
        c.execute("""
            INSERT INTO access_settings (content_type, allowed_roles) 
            VALUES (%s, %s)
            ON CONFLICT (content_type) DO NOTHING
        """, ('trailer', '["owner", "admin"]'))  # Владелец и админы
        
        c.execute("""
            INSERT INTO access_settings (content_type, allowed_roles) 
            VALUES (%s, %s)
            ON CONFLICT (content_type) DO NOTHING
        """, ('news', '["owner", "admin", "user"]'))  # Все авторизованные
        
        conn.commit()
        print("✅ База данных инициализирована успешно.")
        
    except Exception as e:
        print(f"❌ Ошибка при инициализации базы данных: {e}")
        conn.rollback()
    finally:
        conn.close()

# --- Функции для работы с данными ---

def get_all_moments():
    """Получить все моменты из кино"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM moments ORDER BY created_at DESC")
        moments = c.fetchall()
        # Преобразуем из RealDictRow в кортежи для совместимости с текущим кодом
        return [tuple(moment.values()) for moment in moments]
    finally:
        conn.close()

def get_all_trailers():
    """Получить все трейлеры"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM trailers ORDER BY created_at DESC")
        trailers = c.fetchall()
        return [tuple(trailer.values()) for trailer in trailers]
    finally:
        conn.close()

def get_all_news():
    """Получить все новости"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM news ORDER BY created_at DESC")
        news = c.fetchall()
        return [tuple(item.values()) for item in news]
    finally:
        conn.close()

def add_moment(title, description, video_url):
    """Добавить момент из кино"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO moments (title, description, video_url) VALUES (%s, %s, %s)",
                  (title, description, video_url))
        conn.commit()
    finally:
        conn.close()

def add_trailer(title, description, video_url):
    """Добавить трейлер"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO trailers (title, description, video_url) VALUES (%s, %s, %s)",
                  (title, description, video_url))
        conn.commit()
    finally:
        conn.close()

def add_news(title, text, image_url):
    """Добавить новость"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO news (title, text, image_url) VALUES (%s, %s, %s)",
                  (title, text, image_url))
        conn.commit()
    finally:
        conn.close()

def delete_moment(moment_id):
    """Удалить момент из кино"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM moments WHERE id = %s", (moment_id,))
        c.execute("DELETE FROM comments WHERE item_type = 'moment' AND item_id = %s", (moment_id,))
        c.execute("DELETE FROM reactions WHERE item_type = 'moment' AND item_id = %s", (moment_id,))
        conn.commit()
    finally:
        conn.close()

def delete_trailer(trailer_id):
    """Удалить трейлер"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM trailers WHERE id = %s", (trailer_id,))
        c.execute("DELETE FROM comments WHERE item_type = 'trailer' AND item_id = %s", (trailer_id,))
        c.execute("DELETE FROM reactions WHERE item_type = 'trailer' AND item_id = %s", (trailer_id,))
        conn.commit()
    finally:
        conn.close()

def delete_news(news_id):
    """Удалить новость"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM news WHERE id = %s", (news_id,))
        c.execute("DELETE FROM comments WHERE item_type = 'news' AND item_id = %s", (news_id,))
        c.execute("DELETE FROM reactions WHERE item_type = 'news' AND item_id = %s", (news_id,))
        conn.commit()
    finally:
        conn.close()

def get_reactions_count(item_type, item_id):
    """Получить количество реакций для элемента"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("""
            SELECT reaction, COUNT(*) AS count
            FROM reactions 
            WHERE item_type = %s AND item_id = %s 
            GROUP BY reaction
        """, (item_type, item_id))
        results = c.fetchall()
        
        reactions = {'like': 0, 'dislike': 0, 'star': 0, 'fire': 0}
        for row in results:
            # row - это RealDictRow, обращаемся по ключам
            reactions[row['reaction']] = row['count']
        return reactions
    finally:
        conn.close()

def add_reaction(item_type, item_id, user_id, reaction):
    """Добавить реакцию"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        # Удаляем существующую реакцию того же типа от этого пользователя
        c.execute("""
            DELETE FROM reactions 
            WHERE item_type = %s AND item_id = %s AND user_id = %s AND reaction = %s
        """, (item_type, item_id, user_id, reaction))
        
        # Добавляем новую реакцию
        c.execute("""
            INSERT INTO reactions (item_type, item_id, user_id, reaction) 
            VALUES (%s, %s, %s, %s)
        """, (item_type, item_id, user_id, reaction))
        conn.commit()
        return True
    except Exception as e:
        print(f"Ошибка при добавлении реакции: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_comments(item_type, item_id):
    """Получить комментарии для элемента"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("""
            SELECT user_name, text, created_at 
            FROM comments 
            WHERE item_type = %s AND item_id = %s 
            ORDER BY created_at DESC
        """, (item_type, item_id))
        comments = c.fetchall()
        # Преобразуем из RealDictRow в кортежи
        return [tuple(comment.values()) for comment in comments]
    finally:
        conn.close()

def add_comment(item_type, item_id, user_name, text):
    """Добавить комментарий"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO comments (item_type, item_id, user_name, text) 
            VALUES (%s, %s, %s, %s)
        """, (item_type, item_id, user_name, text))
        conn.commit()
    finally:
        conn.close()

def authenticate_admin(username, password):
    """Проверка авторизации администратора"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT password_hash FROM admins WHERE username = %s", (username,))
        result = c.fetchone()
        if result:
            stored_hash = result['password_hash']
            # Проверяем, является ли stored_hash bytes, если нет - конвертируем
            if isinstance(stored_hash, str):
                stored_hash = stored_hash.encode('utf-8')
            return bcrypt.checkpw(password.encode('utf-8'), stored_hash)
        return False
    finally:
        conn.close()

def get_stats():
    """Получить статистику"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT COUNT(*) FROM moments")
        moments_count = c.fetchone()['count']
        c.execute("SELECT COUNT(*) FROM trailers")
        trailers_count = c.fetchone()['count']
        c.execute("SELECT COUNT(*) FROM news")
        news_count = c.fetchone()['count']
        c.execute("SELECT COUNT(*) FROM comments")
        comments_count = c.fetchone()['count']
        
        return {
            'moments': moments_count,
            'trailers': trailers_count,
            'news': news_count,
            'comments': comments_count
        }
    finally:
        conn.close()

def get_or_create_user(telegram_id, username=None, first_name=None, last_name=None):
    """Получить или создать пользователя по Telegram ID"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        # Проверяем, существует ли пользователь
        c.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
        user = c.fetchone()
        
        if user:
            # Обновляем информацию о пользователе
            c.execute("""
                UPDATE users 
                SET username = %s, first_name = %s, last_name = %s 
                WHERE telegram_id = %s
            """, (username, first_name, last_name, telegram_id))
            # Возвращаем обновленного пользователя
            c.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
            updated_user = c.fetchone()
            conn.commit()
            return tuple(updated_user.values())
        else:
            # Создаем нового пользователя с ролью 'user' по умолчанию
            c.execute("""
                INSERT INTO users (telegram_id, username, first_name, last_name, role) 
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
            """, (telegram_id, username, first_name, last_name, 'user'))
            new_user = c.fetchone()
            conn.commit()
            return tuple(new_user.values())
    finally:
        conn.close()

def get_user_by_telegram_id(telegram_id):
    """Получить пользователя по Telegram ID"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
        user = c.fetchone()
        if user:
            return tuple(user.values())
        return None
    finally:
        conn.close()

def get_user_role(telegram_id):
    """Получить роль пользователя по Telegram ID"""
    user = get_user_by_telegram_id(telegram_id)
    if user:
        # Роль находится в 6-м столбце (индекс 5)
        return user[5] 
    return 'guest'  # По умолчанию гость

def get_access_settings(content_type):
    """Получить настройки доступа для типа контента"""
    print(f"!!! DB: get_access_settings called with content_type={content_type} !!!")
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT allowed_roles FROM access_settings WHERE content_type = %s", (content_type,))
        result = c.fetchone()
        print(f"!!! DB: get_access_settings query result={result} !!!")
        if result:
            try:
                # result['allowed_roles'] уже строка JSON
                roles_list = json.loads(result['allowed_roles'])
                print(f"!!! DB: get_access_settings returning parsed list: {roles_list} !!!")
                return roles_list
            except json.JSONDecodeError:
                print("!!! DB: get_access_settings JSON decode error, returning default ['owner'] !!!")
                return ['owner']
        print("!!! DB: get_access_settings returning default ['owner'] !!!")
        return ['owner']  # По умолчанию только владелец
    finally:
        conn.close()

def update_access_settings(content_type, allowed_roles):
    """Обновить настройки доступа"""
    print(f"!!! DB: update_access_settings called with content_type={content_type}, allowed_roles={allowed_roles} !!!")
    conn = get_db_connection()
    c = conn.cursor()
    try:
        # Преобразуем список ролей в JSON строку
        roles_json = json.dumps(allowed_roles)
        print(f"!!! DB: Trying to update with roles_json={roles_json} !!!")
        # Обновляем настройки доступа
        c.execute("UPDATE access_settings SET allowed_roles = %s WHERE content_type = %s", 
                  (roles_json, content_type))
        print(f"!!! DB: UPDATE executed, rowcount={c.rowcount} !!!")
        conn.commit()
        print("!!! DB: Commit successful !!!")
        return True
    except Exception as e:
        print(f"!!! DB: Error during UPDATE/commit: {e} !!!")
        conn.rollback()
        return False
    finally:
        conn.close()

# Инициализация базы данных при импорте
# init_db() # Не будем вызывать init_db здесь, чтобы избежать ошибок при импорте до установки DATABASE_URL
