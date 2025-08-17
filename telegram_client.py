from telethon import TelegramClient

api_id = 20307782
api_hash = '8408f037ff82f1cf2270ae0d41823fe4'
phone_number = '+79832438267'

client = TelegramClient('session_name', api_id, api_hash)

async def main():
    # Старт клиента
    await client.start(phone=phone_number)
    print("✅ Клиент подключен!")

    # Проверка: кто мы
    me = await client.get_me()
    print(f"Вы вошли как: {me.first_name} (@{me.username})")

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
