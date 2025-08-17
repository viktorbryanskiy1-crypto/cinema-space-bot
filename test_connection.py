import os
import psycopg2
import redis
from dotenv import load_dotenv

load_dotenv()

# Проверка Postgres
try:
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    print("Postgres подключение: успешно")
    conn.close()
except Exception as e:
    print("Postgres ошибка:", e)

# Проверка Redis
try:
    r = redis.from_url(os.getenv("REDIS_URL"))
    r.set("test", "ok")
    print("Redis подключение: успешно, test =", r.get("test"))
except Exception as e:
    print("Redis ошибка:", e)
