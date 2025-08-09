import sqlite3
import os
from datetime import datetime

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

# Инициализация базы данных при импорте
init_db()
