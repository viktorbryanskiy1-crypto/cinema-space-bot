from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError
import asyncio
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Вставь свои данные от Telegram API
api_id = 20307782
api_hash = '8408f037ff82f1cf2270ae0d41823fe4'
phone_number = '+79832438267'

async def main():
    print("🚀 Создание клиента...")
    
    # Создаём клиент
    client = TelegramClient('session_name', api_id, api_hash)
    
    try:
        print("📞 Подключение к Telegram...")
        # Подключаемся с таймаутом
        await asyncio.wait_for(client.connect(), timeout=30.0)
        print("✅ Подключение успешно")
        
        # Проверяем авторизацию
        is_authorized = await client.is_user_authorized()
        print(f"🔑 Авторизован: {is_authorized}")
        
        if not is_authorized:
            print("🔐 Начинаем процесс авторизации...")
            # Отправляем код
            print("📤 Отправка кода...")
            await client.send_code_request(phone_number)
            print("📝 Введите код из Telegram:")
            code = input("Код: ")
            
            try:
                await client.sign_in(phone_number, code)
                print("✅ Вход выполнен")
            except SessionPasswordNeededError:
                password = input("Введите пароль 2FA: ")
                await client.sign_in(password=password)
                print("✅ Вход с 2FA выполнен")
        else:
            print("✅ Уже авторизован")
            
        # Теперь пробуем получить данные
        print("📋 Получение диалогов...")
        dialogs = await client.get_dialogs(limit=10)
        for dialog in dialogs:
            if dialog.is_channel:
                username = getattr(dialog.entity, 'username', 'нет')
                print(f"- {dialog.name} (@{username})")
                
    except asyncio.TimeoutError:
        print("❌ Таймаут подключения")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        logging.exception("Подробности ошибки")
    finally:
        try:
            await client.disconnect()
            print("🔚 Клиент отключен")
        except:
            pass

if __name__ == '__main__':
    print("🚀 Запуск Telegram клиента...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  Прервано пользователем")
    except Exception as e:
        print(f"❌ Ошибка запуска: {e}")
