from telethon import TelegramClient

# Вставь сюда свои данные
api_id = YOUR_API_ID       # число, выданное Telegram
api_hash = 'YOUR_API_HASH' # строка, выданная Telegram
phone_number = '+7XXXXXXXXXX'  # твой номер телефона с кодом страны

# Создаем клиент
client = TelegramClient('session_name', api_id, api_hash)

async def main():
    await client.start(phone=phone_number)
    print("✅ Клиент подключен!")

    # Пример: получаем последние 5 сообщений из твоей группы
    group_username = 'YourGroupUsername'  # @username группы
    async for message in client.iter_messages(group_username, limit=5):
        print(message.id, message.text, message.media)

# Запуск клиента
if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
