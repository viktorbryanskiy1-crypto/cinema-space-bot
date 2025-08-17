from telethon import TelegramClient

api_id = 20307782       # твой api_id
api_hash = '8408f037ff82f1cf2270ae0d41823fe4'  # твой api_hash
phone_number = '+79832438267'  # твой номер телефона

client = TelegramClient('session_name', api_id, api_hash)

async def main():
    await client.start(phone=phone_number)
    print("✅ Клиент подключен!")

    # Выводим все диалоги (чат, каналы, группы), в которых ты участвуешь
    async for dialog in client.iter_dialogs():
        if dialog.is_channel:
            print(f"Название канала: {dialog.name}")
            print(f"ID канала: {dialog.id}")
            print(f"Username: {dialog.username}\n")

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
