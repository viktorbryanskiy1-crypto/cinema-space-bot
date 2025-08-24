# Используем официальный образ Python как базовый
FROM python:3.9-slim

# Установим зависимости для сборки некоторых Python-пакетов
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    ffmpeg \ 
    && rm -rf /var/lib/apt/lists/*

# Создаём рабочую директорию внутри контейнера
WORKDIR /app

# Копируем файлы зависимостей
COPY requirements.txt .

# Устанавливаем Python-зависимости
# Используем --no-cache-dir для экономии места, 
# и PIP_NO_CACHE_DIR=1 для pip>=20.1
# --prefer-binary может ускорить установку, если бинарники доступны
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Копируем остальные файлы проекта
COPY . .

# Создаём директорию для загрузок (если нужно)
RUN mkdir -p uploads

# Открываем порт (Railway сам его пробросит)
EXPOSE 10000

# Команда запуска приложения
# Gunicorn будет брать порт из переменной окружения PORT, заданной Railway
CMD ["sh", "-c", "python database.py && gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 120 app:app"]
