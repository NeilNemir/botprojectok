import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from handlers import router
from generators import init_db, seed_approver_if_empty

# === ВАЖНО ===
# Пока токен остаётся в коде (как и было). Позже вынесем в .env.
import os

# читаем токен из переменной окружения BOT_TOKEN
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env var is not set")

# Согласующий по умолчанию (если в БД ещё пусто) — будет проставлен при старте
DEFAULT_APPROVER_ID = 8189816731
# Пользователь для ознакомления с оплатами
DEFAULT_VIEWER_ID = 5874817910

async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    # Инициализация БД + авто-миграции
    init_db()

    # Если approver ещё не задан — проставим дефолтный
    seed_approver_if_empty(DEFAULT_APPROVER_ID, DEFAULT_VIEWER_ID)

    bot = Bot(token=BOT_TOKEN)
    me = await bot.get_me()
    logging.info(f"✅ Bot started as @{me.username} (id={me.id})")

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    logging.info("🚀 Start polling…")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
