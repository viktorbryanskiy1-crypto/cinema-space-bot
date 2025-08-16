# database.py
import psycopg2
import os
from datetime import datetime
import bcrypt
import json
from psycopg2.extras import RealDictCursor

def get_db_connection():
    """Получить подключение к базе данных PostgreSQL"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise Exception("DATABASE_URL environment variable is not set")
    conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
    return conn

def init_db():
    """Инициализация базы данных PostgreSQL"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        # Таблицы
        c.execute("""
            CREATE TABLE IF NOT EXISTS moments (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                video_url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS trailers (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                video_url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                text TEXT,
                image_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS news_blocks (
                id SERIAL PRIMARY KEY,
                news_id INTEGER NOT NULL REFERENCES news(id) ON DELETE CASCADE,
                block_type TEXT NOT NULL,
                content TEXT NOT NULL,
                position INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id SERIAL PRIMARY KEY,
                item_type TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
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
        c.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash BYTEA NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id TEXT UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                role TEXT DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS access_settings (
                id SERIAL PRIMARY KEY,
                content_type TEXT UNIQUE NOT NULL,
                allowed_roles TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Админ по умолчанию
        password_hash = bcrypt.hashpw('admin'.encode('utf-8'), bcrypt.gensalt())
        c.execute("""
            INSERT INTO admins (username, password_hash)
            VALUES (%s, %s)
            ON CONFLICT (username) DO NOTHING
        """, ('admin', password_hash))

        # Владелец
        c.execute("""
            INSERT INTO users (telegram_id, username, first_name, last_name, role)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (telegram_id) DO NOTHING
        """, ('993856446', 'owner_user', 'App', 'Owner', 'owner'))

        # Настройки доступа по умолчанию
        c.execute("""
            INSERT INTO access_settings (content_type, allowed_roles)
            VALUES (%s, %s)
            ON CONFLICT (content_type) DO NOTHING
        """, ('moment', '["owner"]'))
        c.execute("""
            INSERT INTO access_settings (content_type, allowed_roles)
            VALUES (%s, %s)
            ON CONFLICT (content_type) DO NOTHING
        """, ('trailer', '["owner", "admin"]'))
        c.execute("""
            INSERT INTO access_settings (content_type, allowed_roles)
            VALUES (%s, %s)
            ON CONFLICT (content_type) DO NOTHING
        """, ('news', '["owner", "admin", "user"]'))

        conn.commit()
        print("✅ База данных инициализирована успешно.")
    except Exception as e:
        print(f"❌ Ошибка при инициализации базы данных: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

# --- Моменты ---
def get_all_moments():
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM moments ORDER BY created_at DESC")
        moments = c.fetchall()
        return [tuple(m.values()) for m in moments]
    finally:
        conn.close()

def get_moment_by_id(moment_id):
    """Получить один момент по id. Возвращает tuple (как в get_all_moments) или None."""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM moments WHERE id = %s", (moment_id,))
        row = c.fetchone()
        if not row:
            return None
        # Возвращаем в том же формате, что и get_all_moments (tuple)
        return tuple(row.values())
    finally:
        conn.close()

def add_moment(title, description, video_url):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO moments (title, description, video_url) VALUES (%s, %s, %s)",
                  (title, description, video_url))
        conn.commit()
    finally:
        conn.close()

def delete_moment(moment_id):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM moments WHERE id=%s", (moment_id,))
        c.execute("DELETE FROM comments WHERE item_type='moment' AND item_id=%s", (moment_id,))
        c.execute("DELETE FROM reactions WHERE item_type='moment' AND item_id=%s", (moment_id,))
        conn.commit()
    finally:
        conn.close()

# --- Трейлеры ---
def get_all_trailers():
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM trailers ORDER BY created_at DESC")
        trailers = c.fetchall()
        return [tuple(t.values()) for t in trailers]
    finally:
        conn.close()

def add_trailer(title, description, video_url):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO trailers (title, description, video_url) VALUES (%s, %s, %s)",
                  (title, description, video_url))
        conn.commit()
    finally:
        conn.close()

def delete_trailer(trailer_id):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM trailers WHERE id=%s", (trailer_id,))
        c.execute("DELETE FROM comments WHERE item_type='trailer' AND item_id=%s", (trailer_id,))
        c.execute("DELETE FROM reactions WHERE item_type='trailer' AND item_id=%s", (trailer_id,))
        conn.commit()
    finally:
        conn.close()

# --- Новости ---
def get_all_news():
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM news ORDER BY created_at DESC")
        news = c.fetchall()
        return [tuple(n.values()) for n in news]
    finally:
        conn.close()

def add_news(title, text, image_url=None):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO news (title, text, image_url) VALUES (%s, %s, %s)",
                  (title, text, image_url))
        conn.commit()
    finally:
        conn.close()

def delete_news(news_id):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM news WHERE id=%s", (news_id,))
        c.execute("DELETE FROM comments WHERE item_type='news' AND item_id=%s", (news_id,))
        c.execute("DELETE FROM reactions WHERE item_type='news' AND item_id=%s", (news_id,))
        conn.commit()
    finally:
        conn.close()

# --- Блоки новостей ---
def add_news_with_blocks(title, blocks):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO news (title) VALUES (%s) RETURNING id", (title,))
        news_id = c.fetchone()['id']
        for block in blocks:
            c.execute("INSERT INTO news_blocks (news_id, block_type, content, position) VALUES (%s, %s, %s, %s)",
                      (news_id, block['type'], block['content'], block['position']))
        conn.commit()
        return news_id
    finally:
        conn.close()

def get_news_with_blocks():
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM news ORDER BY created_at DESC")
        news_items = c.fetchall()
        result = []
        for news in news_items:
            news_id = news['id']
            c.execute("SELECT block_type, content, position FROM news_blocks WHERE news_id=%s ORDER BY position ASC, created_at ASC", (news_id,))
            blocks = c.fetchall()
            news_data = dict(news)
            news_data['blocks'] = [dict(b) for b in blocks]
            result.append(news_data)
        return result
    finally:
        conn.close()

# --- Комментарии ---
def get_comments(item_type, item_id):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT user_name, text, created_at FROM comments WHERE item_type=%s AND item_id=%s ORDER BY created_at DESC",
                  (item_type, item_id))
        comments = c.fetchall()
        return [tuple(c.values()) for c in comments]
    finally:
        conn.close()

def add_comment(item_type, item_id, user_name, text):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO comments (item_type, item_id, user_name, text) VALUES (%s, %s, %s, %s)",
                  (item_type, item_id, user_name, text))
        conn.commit()
    finally:
        conn.close()

# --- Реакции ---
def get_reactions_count(item_type, item_id):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT reaction, COUNT(*) AS count FROM reactions WHERE item_type=%s AND item_id=%s GROUP BY reaction",
                  (item_type, item_id))
        results = c.fetchall()
        reactions = {'like':0,'dislike':0,'star':0,'fire':0}
        for r in results:
            reactions[r['reaction']] = r['count']
        return reactions
    finally:
        conn.close()

def add_reaction(item_type, item_id, user_id, reaction):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM reactions WHERE item_type=%s AND item_id=%s AND user_id=%s AND reaction=%s",
                  (item_type, item_id, user_id, reaction))
        c.execute("INSERT INTO reactions (item_type, item_id, user_id, reaction) VALUES (%s, %s, %s, %s)",
                  (item_type, item_id, user_id, reaction))
        conn.commit()
        return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()

# --- Пользователи ---
def get_or_create_user(telegram_id, username=None, first_name=None, last_name=None):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM users WHERE telegram_id=%s", (telegram_id,))
        user = c.fetchone()
        if user:
            c.execute("UPDATE users SET username=%s, first_name=%s, last_name=%s WHERE telegram_id=%s",
                      (username, first_name, last_name, telegram_id))
            conn.commit()
            c.execute("SELECT * FROM users WHERE telegram_id=%s", (telegram_id,))
            user = c.fetchone()
            return tuple(user.values())
        else:
            c.execute("INSERT INTO users (telegram_id, username, first_name, last_name, role) VALUES (%s,%s,%s,%s,%s) RETURNING *",
                      (telegram_id, username, first_name, last_name, 'user'))
            new_user = c.fetchone()
            conn.commit()
            return tuple(new_user.values())
    finally:
        conn.close()

def get_user_by_telegram_id(telegram_id):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM users WHERE telegram_id=%s", (telegram_id,))
        user = c.fetchone()
        if user:
            return tuple(user.values())
        return None
    finally:
        conn.close()

def get_user_role(telegram_id):
    user = get_user_by_telegram_id(telegram_id)
    if user:
        return user[5]
    return 'guest'

# --- Настройки доступа ---
def get_access_settings(content_type):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT allowed_roles FROM access_settings WHERE content_type=%s", (content_type,))
        result = c.fetchone()
        if result:
            try:
                return json.loads(result['allowed_roles'])
            except:
                return ['owner']
        return ['owner']
    finally:
        conn.close()

def update_access_settings(content_type, allowed_roles):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        roles_json = json.dumps(allowed_roles)
        c.execute("UPDATE access_settings SET allowed_roles=%s WHERE content_type=%s", (roles_json, content_type))
        conn.commit()
        return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()

# --- Аутентификация админа ---
def authenticate_admin(username, password):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT password_hash FROM admins WHERE username=%s", (username,))
        result = c.fetchone()
        if result:
            stored_hash = result['password_hash']
            if isinstance(stored_hash, memoryview):
                stored_hash = bytes(stored_hash)
            return bcrypt.checkpw(password.encode('utf-8'), stored_hash)
        return False
    finally:
        conn.close()

# --- Статистика ---
def get_stats():
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

# Инициализация базы данных при импорте
# init_db() # Вызывать вручную после установки DATABASE_URL
