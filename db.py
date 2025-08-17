import psycopg2
from psycopg2.extras import RealDictCursor

DB_HOST = "dpg-d2dis5c9c44c73fa50q0-a.oregon-postgres.render.com"
DB_PORT = "5432"
DB_NAME = "cinema_db_jvvx"
DB_USER = "cinema_db_jvvx_user"
DB_PASSWORD = "jh0QW70EhxsKHx3mEq4CqGRSRhua7F5n"

def get_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT,
        cursor_factory=RealDictCursor
    )
    return conn

def get_all_videos():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM videos ORDER BY uploaded_at DESC;")
    videos = cur.fetchall()
    cur.close()
    conn.close()
    return videos

if __name__ == "__main__":
    videos = get_all_videos()
    print(videos)
