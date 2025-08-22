import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from handlers import router
from generators import init_db, seed_approvers_if_empty

# === ВАЖНО ===
# Пока токен остаётся в коде (как и было). Позже вынесем в .env.
import os

# читаем токен из переменной окружения BOT_TOKEN
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env var is not set")

# Согласующие по умолчанию (если в БД ещё пусто) — будут проставлены при старте
DEFAULT_APPROVER1_ID = 5874817910
DEFAULT_APPROVER2_ID = 8189816731

async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    # Инициализация БД + авто-миграции
    init_db()

    # Если approver1/2 ещё не заданы — проставим дефолтные
    seed_approvers_if_empty(DEFAULT_APPROVER1_ID, DEFAULT_APPROVER2_ID)

    bot = Bot(token=BOT_TOKEN)
    me = await bot.get_me()
    logging.info(f"✅ Bot started as @{me.username} (id={me.id})")

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    logging.info("🚀 Start polling…")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
