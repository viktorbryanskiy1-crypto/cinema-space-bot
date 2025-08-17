from telethon import TelegramClient

api_id = 20307782
api_hash = '8408f037ff82f1cf2270ae0d41823fe4'
phone_number = '+7832438267'

client = TelegramClient('session_name', api_id, api_hash)

async def main():
    await client.start(phone=phone_number)
    print("✅ Клиент подключен!")

    # Используем get_entity для приватного или публичного канала
    group = await client.get_entity('kinofilmuni')  # заменяй на ссылку или юзернейм
    async for message in client.iter_messages(group, limit=5):
        print(f"ID: {message.id}")
        if message.text:
            print(f"Текст: {message.text}")
        if message.media:
            print("Есть медиа!")
        print('---------------------')

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
