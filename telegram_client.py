from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
import asyncio
import logging
import sys

# Включаем логирование для отладки
logging.basicConfig(level=logging.DEBUG)

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
    print("✅ Подключение установлено")
    
    # Проверим, авторизованы ли мы
    is_authorized = await client.is_user_authorized()
    print(f"🔑 Статус авторизации: {is_authorized}")
    
    if not is_authorized:
        print("🔑 Необходима авторизация")
        try:
            print("📤 Отправка запроса кода...")
            await client.send_code_request(phone_number)
            print("📝 Ожидание ввода кода...")
            code = input("Please enter the code you received: ")
            print(f"🔢 Введён код: {code}")
            
            # Пробуем авторизоваться с кодом
            try:
                print("🔐 Попытка входа с кодом...")
                await client.sign_in(phone_number, code)
                print("✅ Успешный вход по коду")
            except SessionPasswordNeededError:
                # Если включена двухфакторная аутентификация
                print("🔒 Требуется пароль (2FA)")
                password = input("Please enter your password: ")
                await client.sign_in(password=password)
                print("✅ Успешный вход с паролем")
                
        except Exception as e:
            print(f"❌ Ошибка авторизации: {e}")
            logging.exception("Подробности ошибки авторизации:")
            return
    else:
        print("✅ Уже авторизованы")
    
    print("📋 Получение списка каналов...")
    try:
        count = 0
        async for dialog in client.iter_dialogs():
            # Показываем только каналы
            if dialog.is_channel:
                username = getattr(dialog.entity, 'username', 'нет username')
                print(f"- {dialog.name} (@{username}) | ID: {dialog.id}")
                count += 1
                if count >= 10:  # Ограничиваем для теста
                    break
        print(f"📊 Найдено каналов: {count}")
    except Exception as e:
        print(f"❌ Ошибка при получении диалогов: {e}")
        logging.exception("Подробности ошибки диалогов:")

    print("🔚 Работа завершена")

# Точка входа в программу
if __name__ == '__main__':
    print("🚀 Запуск Telegram клиента...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  Программа прервана пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logging.exception("Подробности критической ошибки:")
