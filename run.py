import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from handlers import router
from generators import init_db, seed_approver_if_empty
from sheet_logger import configure_from_env

# === ВАЖНО ===
# Пока токен остаётся в коде (как и было). Позже вынесем в .env.
import os
from dotenv import load_dotenv  # new
from generators import set_group_id, get_group_id, set_initiator, get_roles

# Загрузим переменные окружения из .env (если файл есть рядом с приложением)
load_dotenv()  # new

# читаем токен из переменной окружения BOT_TOKEN
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env var is not set")

# Согласующий по умолчанию (если в БД ещё пусто) — будет проставлен при старте
DEFAULT_APPROVER_ID = 8189816731
# Пользователь для ознакомления с оплатами
DEFAULT_VIEWER_ID = 5874817910
# Дополнительный инициатор (второй)
DEFAULT_SECONDARY_INITIATOR_ID = 8461014384

# импортируем утилиты конфигурации
from generators import get_config, set_config  # noqa: E402

def bootstrap_env_roles():
    gid = os.getenv("GROUP_ID")
    if gid:
        try:
            set_group_id(int(gid))
        except ValueError:
            print(f"[WARN] Bad GROUP_ID: {gid}")
    inits = os.getenv("INITIATORS")
    if inits:
        for raw in inits.split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                uid = int(raw)
                # Назначаем как initiator если ещё не в списке
                roles = get_roles(uid)
                if "initiator" not in roles:
                    set_initiator(uid)
            except ValueError:
                print(f"[WARN] Bad INITIATOR id: {raw}")

async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    # Инициализация БД + авто-миграции
    init_db()
    # Настройка Google Sheets (если переменные заданы)
    try:
        configure_from_env()
    except Exception as e:
        logging.warning(f"Sheets logger not configured: {e}")

    # Если approver ещё не задан — проставим дефолтный
    seed_approver_if_empty(DEFAULT_APPROVER_ID, DEFAULT_VIEWER_ID)

    # Если второй инициатор не задан — установим дефолтный
    try:
        sec = get_config("secondary_initiator_id", None, int)
        if sec is None and DEFAULT_SECONDARY_INITIATOR_ID:
            set_config("secondary_initiator_id", DEFAULT_SECONDARY_INITIATOR_ID)
            logging.info(f"Seeded secondary_initiator_id={DEFAULT_SECONDARY_INITIATOR_ID}")
    except Exception as e:
        logging.warning(f"Cannot seed secondary initiator: {e}")

    # Bootstrap roles from environment variables
    bootstrap_env_roles()

    bot = Bot(token=BOT_TOKEN)
    me = await bot.get_me()
    logging.info(f"✅ Bot started as @{me.username} (id={me.id})")

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    logging.info("🚀 Start polling…")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
