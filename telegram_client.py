from telethon import TelegramClient

# Вставь сюда свои данные
api_id = 20307782       # число, выданное Telegram
api_hash = '8408f037ff82f1cf2270ae0d41823fe4' # строка, выданная Telegram
phone_number = '+7832438267'  # твой номер телефона с кодом страны

# Создаем клиент
client = TelegramClient('session_name', api_id, api_hash)

async def main():
    await client.start(phone=phone_number)
    print("✅ Клиент подключен!")

    # Пример: получаем последние 5 сообщений из твоей группы
    group_username = 'CinemaSpaceMyBot'  # @username группы
    async for message in client.iter_messages(group_username, limit=5):
        print(message.id, message.text, message.media)

# Запуск клиента
if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
