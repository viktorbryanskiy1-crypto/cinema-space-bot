from telethon import TelegramClient
import asyncio

# Вставь свои данные
api_id = 20307782        # Твой API ID
api_hash = '8408f037ff82f1cf2270ae0d41823fe4'  # Твой API Hash
phone_number = '+79832438267'  # Твой номер с кодом страны

# Создаём клиент
client = TelegramClient('session_name', api_id, api_hash)

async def main():
    # Подключаемся, если первый запуск — попросит код из Telegram
    await client.start(phone=phone_number)
    print("✅ Клиент подключен!\n")

    print("📋 Список всех диалогов (каналы, группы, чаты):")
    async for dialog in client.iter_dialogs():
        # Только каналы
        if dialog.is_channel:
            print(f"- {dialog.name} (@{getattr(dialog.entity, 'username', 'нет username')}) | ID: {dialog.id}")

    # Пример: взять канал по username
    channel_username = 'kinofilmuni'  # замените на свой канал
    print(f"\n📝 Последние 5 сообщений канала @{channel_username}:")
    try:
        channel = await client.get_entity(channel_username)
        async for message in client.iter_messages(channel, limit=5):
            print(f"ID: {message.id}")
            if message.text:
                print(f"Текст: {message.text}")
            if message.media:
                print(f"Медиа: {message.media}")
            print("-" * 20)
    except Exception as e:
        print("❌ Ошибка при получении сообщений:", e)

if __name__ == '__main__':
    asyncio.run(main())
