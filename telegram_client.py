from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
import asyncio
import logging
import sys

# Включаем логирование для отладки
logging.basicConfig(level=logging.INFO)

# Вставь свои данные от Telegram API
api_id = 20307782
api_hash = '8408f037ff82f1cf2270ae0d41823fe4'
phone_number = '+79832438267'

# Создаём клиент с именем сессии
client = TelegramClient('session_name', api_id, api_hash)

async def main():
    print("📞 Подключение к Telegram...")
    
    # Попробуем подключиться
    await client.connect()
    
    # Проверим, авторизованы ли мы
    if not await client.is_user_authorized():
        print("🔑 Необходима авторизация")
        try:
            # Отправляем код на номер
            await client.send_code_request(phone_number)
            code = input("Please enter the code you received: ")
            
            # Пробуем авторизоваться с кодом
            try:
                await client.sign_in(phone_number, code)
            except SessionPasswordNeededError:
                # Если включена двухфакторная аутентификация
                password = input("Please enter your password: ")
                await client.sign_in(password=password)
                
        except Exception as e:
            print(f"❌ Ошибка авторизации: {e}")
            return
    else:
        print("✅ Уже авторизованы")
    
    print("✅ Клиент подключен!\n")

    print("📋 Получение списка каналов...")
    try:
        async for dialog in client.iter_dialogs():
            # Показываем только каналы
            if dialog.is_channel:
                username = getattr(dialog.entity, 'username', 'нет username')
                print(f"- {dialog.name} (@{username}) | ID: {dialog.id}")
    except Exception as e:
        print(f"❌ Ошибка при получении диалогов: {e}")

    # Пример: получаем сообщения из конкретного канала
    channel_username = 'kinofilmuni'
    print(f"\n📝 Последние 5 сообщений канала @{channel_username}:")
    try:
        channel = await client.get_entity(channel_username)
        async for message in client.iter_messages(channel, limit=5):
            print(f"ID: {message.id}")
            if message.text:
                print(f"Текст: {message.text}")
            if message.media:
                print(f"Медиа: {type(message.media).__name__}")
            print("-" * 20)
    except Exception as e:
        print(f"❌ Ошибка при получении сообщений: {e}")

# Точка входа в программу
if __name__ == '__main__':
    print("🚀 Запуск Telegram клиента...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  Программа прервана пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logging.exception("Подробности ошибки:")
    finally:
        print("🔚 Работа завершена")
