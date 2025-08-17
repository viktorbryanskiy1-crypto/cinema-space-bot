from telethon import TelegramClient

api_id = 20307782
api_hash = '8408f037ff82f1cf2270ae0d41823fe4'
phone_number = '+7832438267'

client = TelegramClient('session_name', api_id, api_hash)

async def main():
    await client.start(phone=phone_number)
    print("✅ Клиент подключен!")

    group_username = 'kinofilmuni'  # Заменить на юзернейм канала

    async for message in client.iter_messages(group_username, limit=5):
        print(f"ID: {message.id}")
        if message.text:
            print(f"Текст: {message.text}")
        if message.media:
            print(f"Есть медиа: {message.media}")
        print('---------------------')

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
