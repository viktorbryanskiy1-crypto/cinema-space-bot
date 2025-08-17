from telethon import TelegramClient
import asyncio
import logging

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
    
    # Подключаемся и авторизуемся (если нужно)
    await client.start(phone=phone_number)
    print("✅ Авторизация успешна! Клиент подключен!\n")

    print("📋 Получение списка каналов...")
    async for dialog in client.iter_dialogs():
        # Показываем только каналы
        if dialog.is_channel:
            username = getattr(dialog.entity, 'username', 'нет username')
            print(f"- {dialog.name} (@{username}) | ID: {dialog.id}")

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
    finally:
        print("🔚 Работа завершена")
